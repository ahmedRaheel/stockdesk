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
from ..features import taxation, sales, credit as khata
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/sales/{sale_id}/adjustments",
    dependencies=[Depends(authenticated)],
    tags=["Invoice adjustments"],
)


class ReturnBatch(Contract):
    batch: Identifier
    quantity: Quantity


class ReturnedLine(Contract):
    item: Identifier
    quantity: Quantity
    reason: Literal["expired", "damaged", "incorrect", "opened"]
    restock: bool = Field(default=False, strict=True)
    batches: list[ReturnBatch] = Field(default_factory=list, max_length=100)


class RefundReference(Contract):
    source: str = Field(min_length=1, max_length=150)
    reference: str = Field(min_length=1, max_length=500)


class Preview(Contract):
    original_methods: bool = Field(default=False, strict=True)
    revision: int = Field(ge=0, strict=True)
    returns: list[ReturnedLine] = Field(min_length=1, max_length=100)
    replacements: list[SaleLine] = Field(default_factory=list, max_length=100)
    tax_bps: int = Field(default=0, strict=True, ge=0, le=10000)
    prescription_reference: str = Field(default="", max_length=150)


class Commit(Preview):
    approval_id: Identifier | None = None
    request: Identifier
    quote_token: Identifier
    settlement: Literal["cash", "external", "original"] = "cash"
    refund_references: list[RefundReference] = Field(
        default_factory=list, max_length=200
    )
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
    promotion = obj(old.get("promotion_snapshot")) or frozen.get("promotion", {})
    from ..features.promotions import return_groups

    for group in return_groups(promotion):
        pair = set(group)
        pair_items = [i for i in current if i["product"] in pair]
        if any(i["id"] in requests for i in pair_items) and any(
            i["id"] not in requests
            or requests[i["id"]].quantity != Decimal(str(i["quantity"]))
            for i in pair_items
        ):
            fail(
                "Return all remaining qualifying and reward product quantities together for this cross-product offer.",
                409,
            )
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
            if not unit and (
                r.quantity != r.quantity.to_integral_value()
                or any(b.quantity != b.quantity.to_integral_value() for b in r.batches)
            ):
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
    document = await c.fetchrow(
        "SELECT * FROM receivables WHERE tenant=$1 AND sale=$2", tenant, sale_id
    )
    outstanding = (
        await khata.document_balance(c, tenant, document["id"]) if document else 0
    )
    debt_credit = min(credit, max(0, outstanding))
    waiver = max(0, outstanding - debt_credit) if not remaining_items else 0
    available_credit = credit - debt_credit
    result = dict(
        credit=credit,
        debt_credit=debt_credit,
        debt_waiver=waiver,
        outstanding_before=outstanding,
        outstanding_after=outstanding - debt_credit - waiver,
        available_credit=available_credit,
        replacement_total=replacement["total"],
        net=replacement["total"] - available_credit,
        revised_total=total,
        revision=body.revision,
        returns=returns,
    )
    from ..features.refund_sources import plan

    allocation = await plan(c, tenant, sale_id, available_credit, replacement["total"])
    result["payment_allocation"] = allocation
    if body.original_methods:
        if not allocation["available"]:
            fail(allocation["reason"], 409)
        if result["net"] > 0:
            fail(
                "Choose cash or external settlement when collecting additional payment."
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


async def available_batches(c, tenant, sale, product):
    # Use actual previous batch movements, not an assumed FEFO offset. This also
    # supports adjustments recorded before explicit batch selection existed.
    return await c.fetch(
        """
        SELECT b.id AS batch,b.lot,b.expires,
          SUM(-a.quantity) - COALESCE((SELECT SUM(r.quantity) FROM movements r
            JOIN sale_adjustments j ON j.tenant=r.tenant AND r.notes='Adjustment ' || j.id
            WHERE j.tenant=$1 AND j.sale=$4 AND r.product=$2 AND r.batch_id=b.id AND r.type='RETURN'),0) AS available
        FROM movements m JOIN stock_batch_allocations a ON a.movement=m.id AND a.tenant=m.tenant
        JOIN stock_batches b ON b.id=a.batch AND b.tenant=a.tenant
        WHERE m.tenant=$1 AND m.product=$2 AND m.type='SALE' AND m.notes=$3
        GROUP BY b.id,b.lot,b.expires ORDER BY b.expires NULLS LAST,b.id
    """,
        tenant,
        product,
        sale["invoice_number"],
        sale["id"],
    )


def select_batches(batches, line):
    from ..rules import business_date

    available = {b["batch"]: b for b in batches if b["available"] > 0}
    if line.batches:
        if len({b.batch for b in line.batches}) != len(line.batches):
            fail("Choose each returned batch only once.")
        if sum(b.quantity for b in line.batches) != line.quantity:
            fail("Selected batch quantities must equal the return quantity.")
        selected = []
        for part in line.batches:
            batch = available.get(part.batch)
            if not batch or part.quantity > batch["available"]:
                fail(
                    "Selected batch is unavailable or exceeds its remaining sold quantity.",
                    409,
                )
            selected.append((batch, part.quantity))
    else:
        if (
            line.restock
            and len(available) > 1
            and line.quantity != sum(b["available"] for b in available.values())
        ):
            fail(
                "Select the returned batches for a partial return from multiple original batches."
            )
        remaining, selected = line.quantity, []
        for batch in available.values():
            take = min(remaining, batch["available"])
            if take:
                selected.append((batch, take))
                remaining -= take
        if remaining:
            fail(
                "Original batch allocation is unavailable; adjustment was not posted.",
                409,
            )
    if line.restock and any(
        b["expires"] and b["expires"] < business_date() for b, _ in selected
    ):
        fail("Expired batches cannot return to sellable stock.")
    return selected


@router.get("/batches")
async def return_batches(tenant: str, sale_id: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "return")
            sale = await c.fetchrow(
                "SELECT * FROM sales WHERE tenant=$1 AND id=$2", tenant, sale_id
            )
            if not sale:
                fail("Invoice not found.", 404)
            items = await c.fetch(
                "SELECT id,product FROM sale_items WHERE tenant=$1 AND sale=$2",
                tenant,
                sale_id,
            )
            return {
                "revision": sale["revision"],
                "items": [
                    {
                        "item": i["id"],
                        "batches": service.rows(
                            await available_batches(c, tenant, sale, i["product"])
                        ),
                    }
                    for i in items
                ],
            }


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
    signature_body = body.model_dump(mode="json")
    if not signature_body["original_methods"]:
        del signature_body["original_methods"]
    if not signature_body["refund_references"]:
        del signature_body["refund_references"]
    if not signature_body["approval_id"]:
        del signature_body["approval_id"]
    for line in signature_body["returns"]:
        if not line["batches"]:
            del line["batches"]
    signature = json.dumps({"sale": sale_id, **signature_body}, sort_keys=True)
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
            from ..features.transaction_approvals import consume

            await consume(
                c, user, tenant, "adjustment", body.model_dump(mode="json"), sale_id
            )
            net = quote["net"]
            if body.original_methods != (body.settlement == "original"):
                fail(
                    "Preview the selected original-payment settlement before confirming.",
                    409,
                )
            from ..features.refund_sources import checked_references

            payment_plan = quote["payment_allocation"]
            refunds = (
                checked_references(payment_plan, body.refund_references)
                if body.original_methods
                else []
            )
            if not body.original_methods and body.refund_references:
                fail("Refund references apply only to original-payment settlement.")
            cash_refund = (
                payment_plan["cash_refund"]
                if body.original_methods
                else max(0, -net) if body.settlement == "cash" else 0
            )
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
            if ((net and body.settlement == "cash") or cash_refund) and not till:
                fail(
                    "Open your till before recording a cash collection or refund.", 409
                )
            if cash_refund:
                from .retail import till_totals

                session = await c.fetchrow(
                    "SELECT * FROM till_sessions WHERE tenant=$1 AND id=$2",
                    tenant,
                    till,
                )
                balance = await till_totals(c, tenant, session)
                if balance["expected"] < cash_refund:
                    fail("Refund exceeds cash available in the till.", 409)
            aid = service.uid()
            # Allocate returns from the original sold batches, subtracting previous partial returns.
            for r in body.returns:
                item = next(i for i in before["items"] if i["id"] == r.item)
                batches = await available_batches(c, tenant, sale, item["product"])
                allocation = select_batches(batches, r)
                next(line for line in quote["returns"] if line["item"] == r.item)[
                    "allocated_batches"
                ] = [
                    {"batch": b["batch"], "lot": b["lot"], "quantity": str(q)}
                    for b, q in allocation
                ]
                for batch, take in allocation:
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

            await c.execute(
                "UPDATE sales SET original_snapshot=COALESCE(original_snapshot,$1::jsonb),revision=revision+1,subtotal=$2,discount=$3,tax=$4,tax_included=$5,total=$6,paid_now=$6-GREATEST(0,credit_amount-$11),credit_amount=GREATEST(0,credit_amount-$11),tax_snapshot=$7,promotion_snapshot='{}'::jsonb,status=$8 WHERE tenant=$9 AND id=$10",
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
                quote["credit"],
            )
            await khata.apply_return_credit(c, user, tenant, sale_id, aid, quote)
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
                transferred = (
                    payment_plan["transfers"]
                    if payment_plan["available"]
                    else [
                        {
                            "name": "Return credit",
                            "name_ur": "",
                            "method_id": None,
                            "is_cash": False,
                            "amount": min(
                                quote["available_credit"], replacement["total"]
                            ),
                            "origin": {},
                        }
                    ]
                )
                # Carried cash-origin credit is not newly collected cash in this till.
                for part in transferred:
                    if part["amount"]:
                        await c.execute(
                            "INSERT INTO sale_tenders(id,tenant,sale,method_id,method_name,method_name_ur,is_cash,amount,reference,origin,carried_credit) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,true)",
                            service.uid(),
                            tenant,
                            new["id"],
                            part.get("method_id"),
                            part["name"],
                            part["name_ur"],
                            part["is_cash"],
                            part["amount"],
                            aid,
                            json.dumps(part.get("origin", {})),
                        )
                if net > 0:
                    await c.execute(
                        "INSERT INTO sale_tenders(id,tenant,sale,method_name,method_name_ur,is_cash,amount,reference) VALUES($1,$2,$3,$4,'',$5,$6,$7)",
                        service.uid(),
                        tenant,
                        new["id"],
                        "Cash" if cash else "External collection",
                        bool(cash),
                        net,
                        body.reference,
                    )
            if cash_refund:
                await c.execute(
                    "INSERT INTO till_cash_movements(id,tenant,session,request,amount,reason,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
                    service.uid(),
                    tenant,
                    till,
                    "exchange-" + aid,
                    -cash_refund,
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
                "refunds": refunds,
                "source_usage": (
                    payment_plan["usage"] if payment_plan["available"] else None
                ),
                "cash_refund": cash_refund,
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
            from ..features.till_reports import record_return

            await record_return(
                c, tenant, sale_id, user, aid, quote["credit"], sale["tax"] - tax["tax"]
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
        promo = obj(result["sale"].get("promotion_snapshot")) or {}
        from ..features.promotions import return_groups

        result["sale"]["return_pair_products"] = sorted(
            {product for group in return_groups(promo) for product in group}
        )

        result["tenders"] = service.rows(
            await c.fetch(
                "SELECT method_name,method_name_ur,is_cash,amount,reference,carried_credit FROM sale_tenders WHERE tenant=$1 AND sale=$2 ORDER BY id",
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
