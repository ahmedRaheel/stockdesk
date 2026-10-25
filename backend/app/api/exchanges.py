"""Versioned invoice corrections, partial returns and linked replacement checkout."""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from .contracts import Contract, Identifier, Quantity, Money, SaleLine
from .router import User, authenticated
from .. import db, service, security
from ..features import taxation, sales
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/sales/{sale_id}/adjustments",
    dependencies=[Depends(authenticated)],
    tags=["Invoice adjustments"],
)


class ReturnedLine(Contract):
    item: Identifier
    quantity: Quantity
    reason: Literal["expired", "damaged", "incorrect", "opened"]
    restock: bool = Field(default=False, strict=True)


class Preview(Contract):
    revision: int = Field(ge=0, strict=True)
    returns: list[ReturnedLine] = Field(min_length=1, max_length=100)
    replacements: list[SaleLine] = Field(default_factory=list, max_length=100)
    tax_bps: int = Field(default=0, strict=True, ge=0, le=10000)
    prescription_reference: str = Field(default="", max_length=150)


class Commit(Preview):
    request: Identifier
    quote_token: Identifier
    settlement: Literal["cash", "external"] = "cash"
    tendered: Money = 0
    reference: str = Field(default="", max_length=500)


def obj(value):
    return json.loads(value) if isinstance(value, str) else value


def proportional(amount, remaining, original):
    return int(
        (Decimal(amount) * remaining / original).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


async def prepare(c, tenant, sale_id, body):
    sale = await c.fetchrow(
        "SELECT * FROM sales WHERE tenant=$1 AND id=$2", tenant, sale_id
    )
    if not sale:
        fail("Invoice not found.", 404)
    if sale["status"] != "completed" or sale["revision"] != body.revision:
        fail("Invoice changed. Reload before making another adjustment.", 409)
    if sale["revision"] >= 100:
        fail("This invoice has reached the limit of 100 adjustments.", 409)
    if sale["credit_amount"]:
        fail(
            "Partial adjustments for khata invoices are not supported; use the existing full-return workflow.",
            409,
        )
    current = service.rows(
        await c.fetch(
            "SELECT * FROM sale_items WHERE tenant=$1 AND sale=$2 ORDER BY sku",
            tenant,
            sale_id,
        )
    )
    original = obj(sale["original_snapshot"]) or {
        "sale": service.rows([sale])[0],
        "items": current,
    }
    original["sale"].pop("original_snapshot", None)
    old = original["sale"]
    original_items = original["items"]
    frozen = obj(old.get("tax_snapshot")) or {}
    saved = (
        frozen.get("lines") or frozen.get("promotion", {}).get("line_discounts") or []
    )
    discounts = taxation.allocate_discount(
        [i["line_total"] for i in original_items], old["discount"]
    )
    discount_map = {i["product"]: d for i, d in zip(original_items, discounts)}
    discount_map.update({i["product"]: i["discount"] for i in saved})
    tax_map = {i["product"]: i for i in frozen.get("lines", [])}
    if not tax_map:
        taxes = (
            taxation.allocate_discount(
                [i["line_total"] - discount_map[i["product"]] for i in original_items],
                old["tax"],
            )
            if old["tax"] <= old["subtotal"] - old["discount"]
            else []
        )
        tax_map = {
            i["product"]: {
                "tax": t,
                "inclusive": False,
                "name": "Manual invoice tax",
                "name_ur": "",
                "rate_bps": old["tax_bps"],
                "profile_id": None,
            }
            for i, t in zip(original_items, taxes)
        }
    requests = {r.item: r for r in body.returns}
    if len(requests) != len(body.returns) or not set(requests).issubset(
        {i["id"] for i in current}
    ):
        fail("Choose each available invoice item only once.")
    before = {"sale": service.rows([sale])[0], "items": current}
    before["sale"].pop("original_snapshot", None)
    remaining_items, tax_lines, returns = [], [], []
    originals = {i["id"]: i for i in original_items}
    for item in current:
        r = requests.get(item["id"])
        qty = Decimal(str(item["quantity"]))
        if r:
            if r.quantity > qty:
                fail("Return quantity exceeds the remaining invoiced quantity.")
            if r.restock and r.reason != "incorrect":
                fail(
                    "Expired, damaged and opened items cannot return to sellable stock."
                )
            unit = await c.fetchval(
                "SELECT l.fractional FROM products p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id WHERE p.tenant=$1 AND p.id=$2",
                tenant,
                item["product"],
            )
            if not unit and r.quantity != r.quantity.to_integral_value():
                fail("This product requires whole quantities.")
            returns.append(
                {
                    **r.model_dump(mode="json"),
                    "product": item["product"],
                    "name": item["name"],
                    "sku": item["sku"],
                }
            )
            qty -= r.quantity
        if not qty:
            continue
        source = originals[item["id"]]
        oq = Decimal(str(source["quantity"]))
        amount = proportional(source["line_total"], qty, oq)
        deduct = proportional(discount_map[item["product"]], qty, oq)
        tax_data = tax_map.get(
            item["product"],
            {
                "tax": 0,
                "inclusive": False,
                "name": "Manual invoice tax",
                "rate_bps": old["tax_bps"],
                "profile_id": None,
            },
        )
        tax = proportional(tax_data["tax"], qty, oq)
        remaining_items.append({**item, "quantity": str(qty), "line_total": amount})
        tax_lines.append(
            {
                **tax_data,
                "product": item["product"],
                "line_total": amount,
                "discount": deduct,
                "tax": tax,
                "taxable": amount - deduct - (tax if tax_data.get("inclusive") else 0),
            }
        )
    subtotal = sum(i["line_total"] for i in remaining_items)
    discount = sum(i["discount"] for i in tax_lines)
    tax = sum(i["tax"] for i in tax_lines)
    included = sum(i["tax"] for i in tax_lines if i.get("inclusive"))
    total = subtotal - discount + tax - included
    credit = sale["total"] - total
    if credit < 0:
        fail("Invoice allocation is inconsistent.", 409)
    replacement = (
        await taxation.preview(
            c,
            tenant,
            {
                "items": [i.model_dump() for i in body.replacements],
                "tax_bps": body.tax_bps,
            },
        )
        if body.replacements
        else {"total": 0}
    )
    result = dict(
        credit=credit,
        replacement_total=replacement["total"],
        net=replacement["total"] - credit,
        revised_total=total,
        revision=body.revision,
        returns=returns,
    )
    result["quote_token"] = hashlib.sha256(
        json.dumps(
            {
                "body": body.model_dump(include=set(Preview.model_fields), mode="json"),
                "result": result,
                "replacement": replacement,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return (
        result,
        dict(sale),
        original,
        before,
        remaining_items,
        {
            "mode": frozen.get("mode", "manual"),
            "lines": tax_lines,
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "tax_included": included,
            "total": total,
        },
        replacement,
    )


@router.post("/preview")
async def preview(
    tenant: str, sale_id: str, body: Preview, user: User, request: Request
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "return")
            if body.replacements:
                await service.authorize(c, user, tenant, "sale")
            return (await prepare(c, tenant, sale_id, body))[0]


@router.get("")
async def history(tenant: str, sale_id: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "return")
        return {
            "items": [
                obj(r["result"])
                for r in await c.fetch(
                    "SELECT result FROM sale_adjustments WHERE tenant=$1 AND sale=$2 ORDER BY revision DESC",
                    tenant,
                    sale_id,
                )
            ]
        }


@router.post("")
async def commit(tenant: str, sale_id: str, body: Commit, request: Request, user: User):
    security.csrf(request)
    signature = json.dumps(
        {"sale": sale_id, **body.model_dump(mode="json")}, sort_keys=True
    )
    async with db.pool.acquire() as c:
        async with c.transaction():
            business, _ = await service.authorize(c, user, tenant, "return", lock=True)
            if body.replacements:
                await service.authorize(c, user, tenant, "sale")
            prior = await c.fetchrow(
                "SELECT * FROM sale_adjustments WHERE tenant=$1 AND request=$2",
                tenant,
                body.request,
            )
            if prior:
                if prior["signature"] != signature:
                    fail("Submission ID already used for different data.", 409)
                return obj(prior["result"])
            quote, sale, original, before, items, tax, replacement = await prepare(
                c, tenant, sale_id, body
            )
            if quote["quote_token"] != body.quote_token:
                fail("Prices or invoice changed. Review a fresh preview.", 409)
            net = quote["net"]
            if body.settlement == "cash" and body.tendered < max(0, net):
                fail("Cash received is less than the amount to collect.")
            if (net <= 0 or body.settlement != "cash") and body.tendered:
                fail("Cash received applies only when collecting cash.")
            if body.settlement == "external" and net and not body.reference:
                fail("Record the external collection or refund reference.")
            till = await c.fetchval(
                "SELECT id FROM till_sessions WHERE tenant=$1 AND actor=$2 AND status='open'",
                tenant,
                user["id"],
            )
            if net and body.settlement == "cash" and not till:
                fail(
                    "Open your till before recording a cash collection or refund.", 409
                )
            if net < 0 and body.settlement == "cash":
                from .retail import till_totals

                session = await c.fetchrow(
                    "SELECT * FROM till_sessions WHERE tenant=$1 AND id=$2",
                    tenant,
                    till,
                )
                balance = await till_totals(c, tenant, session)
                if balance["expected"] < -net:
                    fail("Refund exceeds cash available in the till.", 409)
            aid = service.uid()
            # Allocate returns from the original sold batches, subtracting previous partial returns.
            for r in body.returns:
                item = next(i for i in before["items"] if i["id"] == r.item)
                batches = await c.fetch(
                    "SELECT a.batch,-a.quantity AS sold, b.expires FROM movements m JOIN stock_batch_allocations a ON a.movement=m.id JOIN stock_batches b ON b.id=a.batch AND b.tenant=a.tenant WHERE m.tenant=$1 AND m.product=$2 AND m.type='SALE' AND m.notes=$3 ORDER BY b.expires NULLS LAST,b.id",
                    tenant,
                    item["product"],
                    sale["invoice_number"],
                )
                previously = Decimal(
                    str(
                        next(i for i in original["items"] if i["id"] == r.item)[
                            "quantity"
                        ]
                    )
                ) - Decimal(str(item["quantity"]))
                if (
                    r.restock
                    and len(batches) > 1
                    and r.quantity != Decimal(str(item["quantity"]))
                ):
                    fail(
                        "A partial return from multiple original batches cannot be restocked without batch inspection; record it as non-sellable."
                    )
                remaining = r.quantity
                for batch in batches:
                    skipped = min(previously, batch["sold"])
                    previously -= skipped
                    take = min(remaining, batch["sold"] - skipped)
                    if not take:
                        continue
                    if r.restock and batch["expires"]:
                        from ..rules import business_date

                        if batch["expires"] < business_date():
                            fail("Expired batches cannot return to sellable stock.")
                    mid = service.uid()
                    await c.execute(
                        "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,batch_id) VALUES($1,$2,$3,$4,'RETURN',$5,$6,$7)",
                        mid,
                        tenant,
                        item["product"],
                        take,
                        "Adjustment " + aid,
                        user["email"],
                        batch["batch"],
                    )
                    if not r.restock:
                        await c.execute(
                            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,batch_id) VALUES($1,$2,$3,$4,'OUT',$5,$6,$7)",
                            service.uid(),
                            tenant,
                            item["product"],
                            -take,
                            r.reason + " · " + aid,
                            user["email"],
                            batch["batch"],
                        )
                    remaining -= take
                    if remaining == 0:
                        break
                if remaining:
                    fail(
                        "Original batch allocation is unavailable; adjustment was not posted.",
                        409,
                    )
            await c.execute(
                "UPDATE sales SET original_snapshot=COALESCE(original_snapshot,$1::jsonb),revision=revision+1,subtotal=$2,discount=$3,tax=$4,tax_included=$5,total=$6,paid_now=$6,tax_snapshot=$7,promotion_snapshot='{}'::jsonb,status=$8 WHERE tenant=$9 AND id=$10",
                json.dumps(original, default=str),
                tax["subtotal"],
                tax["discount"],
                tax["tax"],
                tax["tax_included"],
                tax["total"],
                json.dumps(tax),
                "completed" if items else "returned",
                tenant,
                sale_id,
            )
            for item in before["items"]:
                left = next((i for i in items if i["id"] == item["id"]), None)
                if left:
                    await c.execute(
                        "UPDATE sale_items SET quantity=$1,line_total=$2 WHERE tenant=$3 AND id=$4",
                        Decimal(left["quantity"]),
                        left["line_total"],
                        tenant,
                        item["id"],
                    )
                else:
                    await c.execute(
                        "DELETE FROM sale_items WHERE tenant=$1 AND id=$2",
                        tenant,
                        item["id"],
                    )
            new = None
            if body.replacements:
                new = await sales.checkout(
                    c,
                    user,
                    dict(
                        tenant=tenant,
                        request="exchange-" + aid,
                        items=[i.model_dump() for i in body.replacements],
                        payment="external",
                        customer=sale["customer"],
                        customer_id=sale["customer_id"],
                        expected=replacement["total"],
                        tax_bps=body.tax_bps,
                        quote_token=replacement.get("quote_token"),
                        prescription_reference=body.prescription_reference,
                    ),
                    business,
                )
                cash = max(0, net) if body.settlement == "cash" else 0
                await c.execute(
                    "UPDATE sales SET cash_amount=$1,tendered=$2,payment=$3 WHERE tenant=$4 AND id=$5",
                    cash,
                    body.tendered,
                    body.settlement if cash else "external",
                    tenant,
                    new["id"],
                )
                await c.execute(
                    "DELETE FROM sale_tenders WHERE tenant=$1 AND sale=$2",
                    tenant,
                    new["id"],
                )
                for label, amount, is_cash in [
                    (
                        "Return credit",
                        min(quote["credit"], replacement["total"]),
                        False,
                    ),
                    (
                        "Cash" if body.settlement == "cash" else "External collection",
                        max(0, net),
                        bool(cash),
                    ),
                ]:
                    if amount:
                        await c.execute(
                            "INSERT INTO sale_tenders(id,tenant,sale,method_name,method_name_ur,is_cash,amount,reference) VALUES($1,$2,$3,$4,'',$5,$6,$7)",
                            service.uid(),
                            tenant,
                            new["id"],
                            label,
                            is_cash,
                            amount,
                            aid,
                        )
            if net < 0 and body.settlement == "cash":
                await c.execute(
                    "INSERT INTO till_cash_movements(id,tenant,session,request,amount,reason,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
                    service.uid(),
                    tenant,
                    till,
                    "exchange-" + aid,
                    net,
                    "Customer refund · " + aid,
                    user["email"],
                )
            result = {
                **quote,
                "id": aid,
                "revision": sale["revision"] + 1,
                "replacement_sale": new["id"] if new else None,
                "replacement_invoice": new["invoice_number"] if new else None,
                "settlement": body.settlement,
                "reference": body.reference,
                "cash_received": body.tendered,
                "change": (
                    body.tendered - max(0, net) if body.settlement == "cash" else 0
                ),
                "actor": user["email"],
                "created": (await c.fetchval("SELECT now()")).isoformat(),
            }
            await c.execute(
                "INSERT INTO sale_adjustments(id,tenant,sale,request,signature,revision,credit,replacement_sale,settlement,net,tendered,reference,before_snapshot,details,result,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)",
                aid,
                tenant,
                sale_id,
                body.request,
                signature,
                result["revision"],
                quote["credit"],
                result["replacement_sale"],
                body.settlement,
                net,
                body.tendered,
                body.reference,
                json.dumps(before, default=str),
                json.dumps(result["returns"]),
                json.dumps(result),
                user["email"],
            )
            await service.audit(c, tenant, user, "Invoice adjusted", result)
            return result


@router.get("/original")
async def original_receipt(tenant: str, sale_id: str, user: User):
    async with db.pool.acquire() as c:
        _, role = await service.authorize(c, user, tenant, "sale")
        saved = await c.fetchval(
            "SELECT original_snapshot FROM sales WHERE tenant=$1 AND id=$2",
            tenant,
            sale_id,
        )
        if not saved:
            fail("No earlier invoice revision exists.", 404)
        result = obj(saved)
        result["sale"].pop("original_snapshot", None)
        result["tenders"] = service.rows(
            await c.fetch(
                "SELECT method_name,method_name_ur,is_cash,amount,reference FROM sale_tenders WHERE tenant=$1 AND sale=$2 ORDER BY id",
                tenant,
                sale_id,
            )
        )
        cash = result["sale"]["cash_amount"]
        result["sale"]["cash_received"] = result["sale"]["tendered"] if cash else 0
        result["sale"]["change"] = (
            max(0, result["sale"]["tendered"] - cash) if cash else 0
        )

        if "cost" not in service.grants(role):
            for item in result["items"]:
                item.pop("cost", None)
        return result
