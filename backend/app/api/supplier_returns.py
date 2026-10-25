"""Receipt-bound supplier returns; goods, credit, and audit commit atomically."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier, Quantity, Money
from .router import User, authenticated
from .payables import get_bill, paid, today, fingerprint, Void
from ..features.supplier_balances import totals
from ..features.reference import lookup
from .. import db, service, security
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/payables/{bill_id}",
    dependencies=[Depends(authenticated)],
    tags=["Supplier returns and refunds"],
)


class Line(Contract):
    source: Identifier
    quantity: Quantity


class Return(Contract):
    request: Identifier
    credit_number: str = Field(min_length=1, max_length=100)
    returned_on: date
    reason_id: Identifier
    reason: str = Field(min_length=1, max_length=500)
    tax: Money = 0
    lines: list[Line] = Field(min_length=1, max_length=100)


class Refund(Contract):
    request: Identifier
    amount: int = Field(strict=True, gt=0, le=100_000_000_000)
    method_id: Identifier
    reference: str = Field(min_length=1, max_length=150)
    received_on: date


async def sources(c, t, b, ids=None, q="", offset=0):
    return service.rows(
        await c.fetch(
            """SELECT s.*,(receipt.created AT TIME ZONE 'Asia/Karachi')::date AS received_date,p.sku,p.name,u.fractional,batch.lot,batch.expires,batch.stock,
 s.quantity-COALESCE((SELECT SUM(l.quantity) FROM supplier_return_lines l WHERE l.tenant=s.tenant AND l.source=s.movement),0) AS source_remaining,
 bl.quantity-COALESCE((SELECT SUM(l.quantity) FROM supplier_return_lines l JOIN supplier_returns r ON r.tenant=l.tenant AND r.id=l.return_id WHERE r.tenant=s.tenant AND r.bill=$3 AND l.product=s.product),0) AS billed_remaining
 FROM purchase_receipt_sources s JOIN purchase_receipts receipt ON receipt.id=s.receipt AND receipt.tenant=s.tenant JOIN supplier_bill_lines bl ON bl.tenant=s.tenant AND bl.bill=$3 AND bl.product=s.product
 JOIN products p ON p.tenant=s.tenant AND p.id=s.product JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id
 JOIN stock_batches batch ON batch.tenant=s.tenant AND batch.id=s.batch
 WHERE s.tenant=$1 AND s.purchase=$2 AND ($4::text[] IS NULL OR s.movement=ANY($4)) AND ($5='' OR strpos(lower(p.sku||' '||p.name||' '||batch.lot),lower($5))>0) ORDER BY p.sku,batch.expires NULLS LAST,s.movement LIMIT $6 OFFSET $7""",
            t,
            b["purchase"],
            b["id"],
            ids,
            q,
            100 if ids else 50,
            offset,
        )
    )


@router.get("/return-options")
async def options(
    tenant: str,
    bill_id: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "supplier_return")
            b = await get_bill(c, tenant, bill_id)
            return {"items": await sources(c, tenant, b, q=q, offset=offset)}


@router.post("/returns", status_code=201)
async def create(
    tenant: str, bill_id: str, payload: Return, request: Request, user: User
):
    security.csrf(request)
    if payload.returned_on > today():
        fail("Return date cannot be in the future.")
    if len({l.source for l in payload.lines}) != len(payload.lines):
        fail("Select each receipt source once.")
    sig = fingerprint({"bill": bill_id, **payload.model_dump(mode="json")})
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "supplier_return", lock=True)
            old = await c.fetchrow(
                "SELECT id,signature FROM supplier_returns WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if old:
                if old["signature"] != sig:
                    fail("Return request identifier already used.", 409)
                return {"id": old["id"]}
            b = await get_bill(c, tenant, bill_id)
            if b["status"] != "posted":
                fail("Cannot return against a voided bill.", 409)
            if payload.returned_on < b["invoice_date"]:
                fail("Return date precedes invoice date.")
            if await c.fetchval(
                "SELECT 1 FROM supplier_returns WHERE tenant=$1 AND supplier=$2 AND credit_number=$3",
                tenant,
                b["supplier"],
                payload.credit_number,
            ):
                fail("Supplier credit number already registered.", 409)
            await lookup(c, tenant, payload.reason_id, "supplier_return_reason")
            rows = {
                x["movement"]: x
                for x in await sources(
                    c, tenant, b, ids=[l.source for l in payload.lines]
                )
            }
            bill_lines = {
                x["product"]: x
                for x in await c.fetch(
                    "SELECT * FROM supplier_bill_lines WHERE tenant=$1 AND bill=$2",
                    tenant,
                    bill_id,
                )
            }
            by_product = {}
            by_batch = {}
            prepared = []
            subtotal = 0
            # Cumulative line allocation avoids rounding drift across repeated fractional returns.
            for line in payload.lines:
                s = rows.get(line.source)
                if not s:
                    fail("Receipt source does not belong to this bill purchase.", 404)
                if payload.returned_on < s["received_date"]:
                    fail("Return date precedes goods receipt date.")
                if not s["fractional"] and line.quantity != int(line.quantity):
                    fail("This product requires whole quantities.")
                if line.quantity > s["source_remaining"]:
                    fail("Return exceeds the unreturned receipt quantity.", 409)
                pid = s["product"]
                qty = by_product.get(pid, Decimal(0)) + line.quantity
                by_product[pid] = qty
                if qty > s["billed_remaining"]:
                    fail("Return exceeds the unreturned billed quantity.", 409)
                batch_qty = by_batch.get(s["batch"], Decimal(0)) + line.quantity
                by_batch[s["batch"]] = batch_qty
                if batch_qty > s["stock"]:
                    fail("Insufficient stock in the selected batch.", 409)
                original = bill_lines[pid]
                previous = (
                    original["quantity"] - s["billed_remaining"] + qty - line.quantity
                )

                def amount(q):
                    return int(
                        (
                            Decimal(original["line_total"]) * q / original["quantity"]
                        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
                    )

                credit = amount(previous + line.quantity) - amount(previous)
                subtotal += credit
                prepared.append((line, s, credit))
            tax_used = await c.fetchval(
                "SELECT COALESCE(SUM(tax),0) FROM supplier_returns WHERE tenant=$1 AND bill=$2",
                tenant,
                bill_id,
            )
            if payload.tax > b["tax"] - tax_used:
                fail("Tax credit exceeds the remaining invoice tax.", 409)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO supplier_returns(id,tenant,bill,supplier,request,signature,credit_number,returned_on,reason_id,reason,subtotal,tax,total,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
                identifier,
                tenant,
                bill_id,
                b["supplier"],
                payload.request,
                sig,
                payload.credit_number,
                payload.returned_on,
                payload.reason_id,
                payload.reason,
                subtotal,
                payload.tax,
                subtotal + payload.tax,
                user["email"],
            )
            for line, s, credit in prepared:
                mid = service.uid()
                await c.execute(
                    "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,batch_id,reason_id) VALUES($1,$2,$3,$4,'OUT',$5,$6,$7,$8)",
                    mid,
                    tenant,
                    s["product"],
                    -line.quantity,
                    "Supplier credit " + payload.credit_number + ": " + payload.reason,
                    user["email"],
                    s["batch"],
                    payload.reason_id,
                )
                await c.execute(
                    "INSERT INTO supplier_return_lines(tenant,return_id,product,source,quantity,subtotal,movement) VALUES($1,$2,$3,$4,$5,$6,$7)",
                    tenant,
                    identifier,
                    s["product"],
                    line.source,
                    line.quantity,
                    credit,
                    mid,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier goods returned",
                {
                    "id": identifier,
                    "bill": bill_id,
                    "total": subtotal + payload.tax,
                    "lines": payload.model_dump(mode="json")["lines"],
                },
            )
            return {"id": identifier}


@router.post("/refunds", status_code=201)
async def refund(
    tenant: str, bill_id: str, payload: Refund, request: Request, user: User
):
    security.csrf(request)
    if payload.received_on > today():
        fail("Refund date cannot be in the future.")
    sig = fingerprint({"bill": bill_id, **payload.model_dump(mode="json")})
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "finance", lock=True)
            old = await c.fetchrow(
                "SELECT id,signature FROM supplier_refunds WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if old:
                if old["signature"] != sig:
                    fail("Refund request identifier already used.", 409)
                return {"id": old["id"]}
            b = await get_bill(c, tenant, bill_id)
            if b["status"] != "posted":
                fail("Cannot refund a voided bill.", 409)
            latest_credit = await c.fetchval(
                "SELECT MAX(returned_on) FROM supplier_returns WHERE tenant=$1 AND bill=$2",
                tenant,
                bill_id,
            )
            if not latest_credit or payload.received_on < latest_credit:
                fail("Refund date must be on or after the latest credit date.")
            balance = await totals(c, tenant, bill_id)
            credit = (
                await paid(c, tenant, bill_id)
                + balance["credited"]
                - b["total"]
                - balance["refunded"]
            )
            if payload.amount > credit:
                fail("Refund exceeds the supplier credit balance.", 409)
            method = await lookup(c, tenant, payload.method_id, "payment_method")
            identifier = service.uid()
            await c.execute(
                "INSERT INTO supplier_refunds(id,tenant,bill,request,signature,amount,method_id,method_name,reference,received_on,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                identifier,
                tenant,
                bill_id,
                payload.request,
                sig,
                payload.amount,
                method["id"],
                method["name"],
                payload.reference,
                payload.received_on,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier refund recorded",
                {
                    "id": identifier,
                    "bill": bill_id,
                    "amount": payload.amount,
                    "reference": payload.reference,
                },
            )
            return {"id": identifier}


@router.post("/refunds/{refund_id}/void")
async def void_refund(
    tenant: str,
    bill_id: str,
    refund_id: str,
    payload: Void,
    request: Request,
    user: User,
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "finance", lock=True)
            r = await c.fetchrow(
                "SELECT * FROM supplier_refunds WHERE tenant=$1 AND bill=$2 AND id=$3",
                tenant,
                bill_id,
                refund_id,
            )
            if not r:
                fail("Supplier refund not found.", 404)
            if r["status"] == "void":
                return {"ok": True}
            await c.execute(
                "UPDATE supplier_refunds SET status='void',voided=now(),void_reason=$1 WHERE tenant=$2 AND id=$3",
                payload.reason,
                tenant,
                refund_id,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier refund voided",
                {"id": refund_id, "bill": bill_id, "reason": payload.reason},
            )
    return {"ok": True}
