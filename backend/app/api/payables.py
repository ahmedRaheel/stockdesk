"""Supplier subledger. Caller-supplied totals never override matched purchase costs.

All writes take the same tenant lock as receiving. Posted documents are immutable;
voids preserve provenance. Payment recording does not call an external payment rail.
"""

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier, Money, Quantity
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail
from ..features.reference import lookup
from ..features.supplier_balances import totals

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/payables",
    dependencies=[Depends(authenticated)],
    tags=["Supplier payables"],
)


class Line(Contract):
    product: Identifier
    quantity: Quantity
    unit_cost: Money


class Bill(Contract):
    request: Identifier
    purchase: Identifier
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date
    tax: Money = 0
    lines: list[Line] = Field(min_length=1, max_length=100)


class Payment(Contract):
    request: Identifier
    amount: int = Field(strict=True, gt=0, le=100_000_000_000)
    method_id: Identifier
    reference: str = Field(min_length=1, max_length=150)
    paid_on: date


class Void(Contract):
    reason: str = Field(min_length=1, max_length=500)


def today():
    return datetime.now(ZoneInfo("Asia/Karachi")).date()


def fingerprint(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


async def auth(c, u, t, lock=False):
    await service.authorize(c, u, t, "finance", lock=lock)


async def get_bill(c, t, i):
    b = await c.fetchrow("SELECT * FROM supplier_bills WHERE tenant=$1 AND id=$2", t, i)
    if not b:
        fail("Supplier bill not found.", 404)
    return b


async def paid(c, t, i):
    return await c.fetchval(
        "SELECT COALESCE(SUM(amount),0) FROM supplier_payments WHERE tenant=$1 AND bill=$2 AND status='posted'",
        t,
        i,
    )


@router.get("")
async def listing(
    tenant: str,
    user: User,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await auth(c, user, tenant)
            rows = await c.fetch(
                """SELECT b.*,s.name AS supplier_name,v.paid,v.credited,v.refunded,v.balance
                FROM supplier_bills b JOIN suppliers s ON s.tenant=b.tenant AND s.id=b.supplier
                JOIN supplier_bill_balances v ON v.tenant=b.tenant AND v.id=b.id
                WHERE b.tenant=$1 ORDER BY b.created DESC,b.id LIMIT $2 OFFSET $3""",
                tenant,
                limit,
                offset,
            )
            summary = await c.fetchrow(
                """WITH balances AS (
                SELECT b.due_date,v.balance FROM supplier_bills b JOIN supplier_bill_balances v ON v.tenant=b.tenant AND v.id=b.id
                WHERE b.tenant=$1 AND b.status='posted')
                SELECT COALESCE(SUM(GREATEST(balance,0)),0) AS outstanding,
                COALESCE(SUM(GREATEST(-balance,0)),0) AS supplier_credit,
                COALESCE(SUM(balance) FILTER(WHERE balance>0 AND due_date >= $2),0) AS not_due,
                COALESCE(SUM(balance) FILTER(WHERE balance>0 AND $2-due_date BETWEEN 1 AND 7),0) AS days_1_7,
                COALESCE(SUM(balance) FILTER(WHERE balance>0 AND $2-due_date BETWEEN 8 AND 30),0) AS days_8_30,
                COALESCE(SUM(balance) FILTER(WHERE balance>0 AND $2-due_date > 30),0) AS days_31_plus FROM balances""",
                tenant,
                today(),
            )
            return {
                "items": service.rows(rows),
                "summary": dict(summary),
                "as_of": today(),
            }


@router.get("/matchable-orders")
async def matchable(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await auth(c, user, tenant)
            orders = await c.fetch(
                "SELECT o.id,o.reference,s.name AS supplier_name FROM purchase_orders o JOIN suppliers s ON s.tenant=o.tenant AND s.id=o.supplier WHERE o.tenant=$1 AND (o.reference ILIKE '%'||$2||'%' OR s.name ILIKE '%'||$2||'%') ORDER BY o.created DESC,o.id LIMIT 50 OFFSET $3",
                tenant,
                q,
                offset,
            )
            result = []
            for o in orders:
                lines = await c.fetch(
                    """SELECT l.*,p.name,p.sku,u.fractional,l.received-COALESCE((SELECT SUM(bl.quantity) FROM supplier_bill_lines bl JOIN supplier_bills b ON b.tenant=bl.tenant AND b.id=bl.bill WHERE b.tenant=l.tenant AND b.purchase=l.purchase AND bl.product=l.product AND b.status='posted'),0) AS unbilled
                FROM purchase_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id WHERE l.tenant=$1 AND l.purchase=$2 ORDER BY p.sku""",
                    tenant,
                    o["id"],
                )
                result.append({**dict(o), "lines": service.rows(lines)})
            return {"items": result}


@router.get("/{identifier}")
async def detail(tenant: str, identifier: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await auth(c, user, tenant)
            b = await get_bill(c, tenant, identifier)
            lines = await c.fetch(
                "SELECT l.*,p.sku,p.name FROM supplier_bill_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product WHERE l.tenant=$1 AND l.bill=$2 ORDER BY p.sku",
                tenant,
                identifier,
            )
            payments = await c.fetch(
                "SELECT * FROM supplier_payments WHERE tenant=$1 AND bill=$2 ORDER BY created,id",
                tenant,
                identifier,
            )
            return {
                "bill": dict(b),
                "lines": service.rows(lines),
                "payments": service.rows(payments),
                "paid": await paid(c, tenant, identifier),
                **await totals(c, tenant, identifier),
                "credits": service.rows(
                    await c.fetch(
                        "SELECT * FROM supplier_returns WHERE tenant=$1 AND bill=$2 ORDER BY created,id",
                        tenant,
                        identifier,
                    )
                ),
                "refunds": service.rows(
                    await c.fetch(
                        "SELECT * FROM supplier_refunds WHERE tenant=$1 AND bill=$2 ORDER BY created,id",
                        tenant,
                        identifier,
                    )
                ),
            }


@router.post("", status_code=201)
async def create(tenant: str, payload: Bill, request: Request, user: User):
    security.csrf(request)
    if payload.due_date < payload.invoice_date or payload.invoice_date > today():
        fail("Check invoice and due dates.")
    if len({x.product for x in payload.lines}) != len(payload.lines):
        fail("Duplicate invoice product.")
    sig = fingerprint(payload.model_dump(mode="json"))
    async with db.pool.acquire() as c:
        async with c.transaction():
            await auth(c, user, tenant, True)
            old = await c.fetchrow(
                "SELECT id,signature FROM supplier_bills WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if old:
                if old["signature"] != sig:
                    fail("Bill request identifier already used.", 409)
                return {"id": old["id"]}
            order = await c.fetchrow(
                "SELECT * FROM purchase_orders WHERE tenant=$1 AND id=$2",
                tenant,
                payload.purchase,
            )
            if not order:
                fail("Purchase order not found.", 404)
            if await c.fetchval(
                "SELECT 1 FROM supplier_bills WHERE tenant=$1 AND supplier=$2 AND invoice_number=$3",
                tenant,
                order["supplier"],
                payload.invoice_number,
            ):
                fail(
                    "Supplier invoice number already registered, including voided bills.",
                    409,
                )
            matched = []
            for line in payload.lines:
                pl = await c.fetchrow(
                    "SELECT * FROM purchase_lines WHERE tenant=$1 AND purchase=$2 AND product=$3",
                    tenant,
                    payload.purchase,
                    line.product,
                )
                if not pl:
                    fail("Invoice product is not on the purchase order.", 409)
                if line.unit_cost != pl["unit_cost"]:
                    fail("Invoice cost differs from the agreed purchase cost.", 409)
                billed = await c.fetchval(
                    "SELECT COALESCE(SUM(l.quantity),0) FROM supplier_bill_lines l JOIN supplier_bills b ON b.tenant=l.tenant AND b.id=l.bill WHERE b.tenant=$1 AND b.purchase=$2 AND l.product=$3 AND b.status='posted'",
                    tenant,
                    payload.purchase,
                    line.product,
                )
                if line.quantity > pl["received"] - billed:
                    fail("Invoice quantity exceeds received, unbilled quantity.", 409)
                fractional = await c.fetchval(
                    "SELECT l.fractional FROM products p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id WHERE p.tenant=$1 AND p.id=$2",
                    tenant,
                    line.product,
                )
                if not fractional and line.quantity != int(line.quantity):
                    fail("This product requires whole quantities.")
                total = int(
                    (line.quantity * Decimal(line.unit_cost)).quantize(
                        Decimal(1), rounding=ROUND_HALF_UP
                    )
                )
                matched.append((line, total))
            subtotal = sum(x[1] for x in matched)
            if not 0 < subtotal + payload.tax <= 100_000_000_000:
                fail("Bill total is outside allowed bounds.")
            i = service.uid()
            await c.execute(
                "INSERT INTO supplier_bills(id,tenant,supplier,purchase,request,signature,invoice_number,invoice_date,due_date,subtotal,tax,total,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                i,
                tenant,
                order["supplier"],
                payload.purchase,
                payload.request,
                sig,
                payload.invoice_number,
                payload.invoice_date,
                payload.due_date,
                subtotal,
                payload.tax,
                subtotal + payload.tax,
                user["email"],
            )
            for line, total in matched:
                await c.execute(
                    "INSERT INTO supplier_bill_lines(tenant,bill,product,quantity,unit_cost,line_total) VALUES($1,$2,$3,$4,$5,$6)",
                    tenant,
                    i,
                    line.product,
                    line.quantity,
                    line.unit_cost,
                    total,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier invoice matched",
                {
                    "id": i,
                    "purchase": payload.purchase,
                    "total": subtotal + payload.tax,
                },
            )
            return {"id": i}


@router.post("/{identifier}/payments", status_code=201)
async def payment(
    tenant: str, identifier: str, payload: Payment, request: Request, user: User
):
    security.csrf(request)
    if payload.paid_on > today():
        fail("Payment date cannot be in the future.")
    sig = fingerprint({"bill": identifier, **payload.model_dump(mode="json")})
    async with db.pool.acquire() as c:
        async with c.transaction():
            await auth(c, user, tenant, True)
            old = await c.fetchrow(
                "SELECT id,signature FROM supplier_payments WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if old:
                if old["signature"] != sig:
                    fail("Payment request identifier already used.", 409)
                return {"id": old["id"]}
            b = await get_bill(c, tenant, identifier)
            if b["status"] != "posted":
                fail("Cannot pay a voided bill.", 409)
            if payload.paid_on < b["invoice_date"]:
                fail("Payment date precedes invoice date.")
            adjustments = await totals(c, tenant, identifier)
            if (
                payload.amount
                > b["total"]
                - await paid(c, tenant, identifier)
                - adjustments["credited"]
                + adjustments["refunded"]
            ):
                fail("Payment exceeds the outstanding bill balance.", 409)
            method = await lookup(c, tenant, payload.method_id, "payment_method")
            i = service.uid()
            await c.execute(
                "INSERT INTO supplier_payments(id,tenant,bill,request,signature,amount,method_id,method_name,reference,paid_on,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                i,
                tenant,
                identifier,
                payload.request,
                sig,
                payload.amount,
                method["id"],
                method["name"],
                payload.reference,
                payload.paid_on,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier payment recorded",
                {
                    "id": i,
                    "bill": identifier,
                    "amount": payload.amount,
                    "reference": payload.reference,
                },
            )
            return {"id": i}


@router.post("/{identifier}/void")
async def void_bill(
    tenant: str, identifier: str, payload: Void, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await auth(c, user, tenant, True)
            b = await get_bill(c, tenant, identifier)
            if b["status"] == "void":
                return {"ok": True}
            if await c.fetchval(
                "SELECT 1 FROM supplier_returns WHERE tenant=$1 AND bill=$2",
                tenant,
                identifier,
            ):
                fail("Bills with supplier returns cannot be voided.", 409)
            if await paid(c, tenant, identifier):
                fail("Void payment records before voiding the bill.", 409)
            await c.execute(
                "UPDATE supplier_bills SET status='void',void_reason=$1,voided=now() WHERE tenant=$2 AND id=$3",
                payload.reason,
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier bill voided",
                {"id": identifier, "reason": payload.reason},
            )
    return {"ok": True}


@router.post("/{identifier}/payments/{payment_id}/void")
async def void_payment(
    tenant: str,
    identifier: str,
    payment_id: str,
    payload: Void,
    request: Request,
    user: User,
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await auth(c, user, tenant, True)
            p = await c.fetchrow(
                "SELECT * FROM supplier_payments WHERE tenant=$1 AND bill=$2 AND id=$3",
                tenant,
                identifier,
                payment_id,
            )
            if not p:
                fail("Supplier payment not found.", 404)
            if p["status"] == "void":
                return {"ok": True}
            await c.execute(
                "UPDATE supplier_payments SET status='void',void_reason=$1,voided=now() WHERE tenant=$2 AND id=$3",
                payload.reason,
                tenant,
                payment_id,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Supplier payment voided",
                {"id": payment_id, "bill": identifier, "reason": payload.reason},
            )
    return {"ok": True}
