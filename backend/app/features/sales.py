"""Sales commands. Caller owns authorization and transaction scope."""

import json
from datetime import date
from . import credit, taxation
from .reference import lookup
from ..rules import clean, number, cart_items, totals, fail, line_amount, business_date
from ..service import uid, audit


async def checkout(c, u, b, t=None):
    tenant = b.get("tenant", "")
    cart = cart_items(b.get("items"))
    request = clean(b.get("request"), "Request ID", 100)
    customer = clean(b.get("customer") or "Walk-in customer", "Customer")
    payment = b.get("payment")
    if payment not in ["cash", "external"]:
        fail("Invalid payment method.")
    discount = number(b.get("discount", 0), "Discount")
    tax_bps = number(b.get("tax_bps", 0), "Tax rate", 0, 10000)
    expected = number(b.get("expected"), "Expected total")
    tendered = number(b.get("tendered", 0), "Cash received")
    customer_id = b.get("customer_id")
    paid_now = b.get("paid_now")
    if paid_now is not None:
        number(paid_now, "Paid now")
    due_raw = b.get("due_date")
    method_id = b.get("payment_method_id")
    prescription_reference = clean(
        b.get("prescription_reference", ""), "Prescription reference", 150, True
    )
    held_id = b.get("held_bill_id")
    promotion_code = clean(
        b.get("promotion_code") or "", "Promotion code", 40, True
    ).upper()
    auto_promotion = b.get("auto_promotion", False)
    if not isinstance(auto_promotion, bool):
        fail("Automatic promotion must be true or false.")
    signature = json.dumps(
        {
            "items": cart,
            **({"promotion_code": promotion_code} if promotion_code else {}),
            **({"auto_promotion": True} if auto_promotion else {}),
            "tenders": b.get("tenders"),
            "quote_token": b.get("quote_token"),
            "prescription_reference": prescription_reference,
            "held_bill_id": held_id,
            "customer_id": customer_id,
            "paid_now": paid_now,
            "due_date": due_raw,
            "payment_method_id": method_id,
            "customer": customer,
            "payment": payment,
            "discount": discount,
            "tax_bps": tax_bps,
            "expected": expected,
            "tendered": tendered,
        },
        sort_keys=True,
        default=str,
    )
    prior = await c.fetchrow(
        "SELECT * FROM sales WHERE tenant=$1 AND request=$2", tenant, request
    )
    if prior:
        original = prior.get("original_snapshot")
        if original:
            prior = (
                json.loads(original)["sale"]
                if isinstance(original, str)
                else original["sale"]
            )
        if prior["signature"] != signature:
            fail("Submission ID already used for different data.")
        return {
            "id": prior["id"],
            "total": prior["total"],
            "invoice_number": prior["invoice_number"],
            "cash_received": prior["tendered"] if prior["cash_amount"] else 0,
            "cash_amount": prior["cash_amount"],
            "change": (
                max(0, prior["tendered"] - prior["cash_amount"])
                if prior["cash_amount"]
                else 0
            ),
            "paid_now": prior["paid_now"],
            "credit_amount": prior["credit_amount"],
        }
    from .transaction_approvals import consume
    await consume(c, u, tenant, "discount", b)
    if held_id:
        held = await c.fetchrow(
            "SELECT * FROM held_bills WHERE tenant=$1 AND id=$2 AND actor=$3 FOR UPDATE",
            tenant,
            held_id,
            u["id"],
        )
        if not held:
            fail("Held bill not found.", 404)
        if held["consumed_sale"]:
            fail("This held bill has already been checked out.", 409)
    products = []
    for item in cart:
        p = await c.fetchrow(
            "SELECT * FROM products WHERE tenant=$1 AND id=$2 AND active=true FOR UPDATE",
            tenant,
            item["id"],
        )
        if not p:
            fail("A product is no longer available.")
        unit = await lookup(c, tenant, p["unit_id"], "unit", allow_inactive=True)
        if (
            not unit["fractional"]
            and item["quantity"] != item["quantity"].to_integral_value()
        ):
            fail("This product requires whole quantities.")
        if p["prescription_required"] and not prescription_reference:
            fail("A prescription reference is required for this product.")
        available = await c.fetchval(
            "SELECT COALESCE(SUM(stock),0) FROM stock_batches WHERE tenant=$1 AND product=$2 AND (expires IS NULL OR expires>=(now() AT TIME ZONE 'Asia/Karachi')::date)",
            tenant,
            p["id"],
        )
        if available < item["quantity"]:
            fail("Insufficient non-expired stock for " + p["name"])
        if p["stock"] < item["quantity"]:
            fail(f"Insufficient stock for {p['name']}. Available: {p['stock']}.")
        products.append(
            {
                **dict(p),
                "quantity": item["quantity"],
                "unit_name": unit["name"],
                "line_total": line_amount(p["price"], item["quantity"]),
            }
        )
    subtotal = sum(p["line_total"] for p in products)
    number(subtotal, "Subtotal")
    tax_quote = await taxation.quote(
        c,
        tenant,
        products,
        discount,
        tax_bps,
        promotion_code,
        customer_id,
        auto_promotion,
    )
    if (tax_quote["mode"] != "manual" or promotion_code or auto_promotion) and b.get(
        "quote_token"
    ) != tax_quote["quote_token"]:
        fail("Tax or prices changed. Refresh the quote and review the total.", 409)
    tax, total = tax_quote["tax"], tax_quote["total"]
    discount = tax_quote["discount"]
    if tax_quote["mode"] != "manual":
        tax_bps = 0
    if total != expected:
        fail("Prices changed. Refresh and review the cart total.")
    paid_now = total if paid_now is None else paid_now
    if paid_now > total:
        fail("Paid amount cannot exceed invoice total; use cash received for change.")
    credit_amount = total - paid_now
    if method_id:
        method = await lookup(c, tenant, method_id, "payment_method")
        if paid_now and (method["code"] == "cash") != (payment == "cash"):
            fail("Payment method must match cash or external collection.")
    if customer_id:
        person = await c.fetchrow(
            "SELECT * FROM customers WHERE tenant=$1 AND id=$2 AND active=true",
            tenant,
            customer_id,
        )
        if not person:
            fail("Customer not found.", 404)
        customer = person["name"]
    if credit_amount:
        if not customer_id:
            fail("Choose a customer for khata credit.")
        from ..service import authorize

        await authorize(c, u, tenant, "credit")
        await credit.check_credit(c, tenant, customer_id, credit_amount)
        try:
            due = date.fromisoformat(due_raw or "")
        except ValueError:
            fail("Choose a valid payment due date.")
        if due < business_date():
            fail("Due date cannot be in the past.")
    parts = []
    if b.get("tenders"):
        from ..api.contracts import Tender

        for raw in b["tenders"]:
            part = Tender.model_validate(raw).model_dump()
            method = await lookup(c, tenant, part["method_id"], "payment_method")
            parts.append(
                {
                    **part,
                    "name": method["name"],
                    "name_ur": method["name_ur"],
                    "is_cash": method["code"] == "cash",
                }
            )
        if sum(p["amount"] for p in parts) != paid_now:
            fail("Payment parts must equal the paid-now amount.")
    elif paid_now:
        method = (
            await lookup(c, tenant, method_id, "payment_method") if method_id else None
        )
        parts = [
            {
                "method_id": method_id,
                "amount": paid_now,
                "reference": "",
                "name": method["name"] if method else payment,
                "name_ur": method["name_ur"] if method else "",
                "is_cash": payment == "cash",
            }
        ]
    cash_amount = sum(p["amount"] for p in parts if p["is_cash"])
    if tendered < cash_amount:
        fail("Cash received is less than the sale total.")
    seq = await c.fetchval(
        "UPDATE tenants SET invoice_seq=invoice_seq+1 WHERE id=$1 RETURNING invoice_seq",
        tenant,
    )
    inv = f"INV-{seq:07d}"
    sid = uid()
    await c.execute(
        "INSERT INTO sales(id,tenant,request,signature,invoice_number,customer,subtotal,discount,tax_bps,tax,total,tendered,payment,seller_name,seller_address,seller_tax_number,currency,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)",
        sid,
        tenant,
        request,
        signature,
        inv,
        customer,
        subtotal,
        discount,
        tax_bps,
        tax,
        total,
        tendered,
        payment,
        t["name"],
        t["address"],
        t["tax_number"],
        t["currency"],
        u["email"],
    )
    await c.execute(
        "UPDATE sales SET customer_id=$1,paid_now=$2,credit_amount=$3,payment_method_id=$4 WHERE tenant=$5 AND id=$6",
        customer_id,
        paid_now,
        credit_amount,
        method_id,
        tenant,
        sid,
    )
    await c.execute(
        "UPDATE sales SET tax_included=$1,tax_snapshot=$2 WHERE tenant=$3 AND id=$4",
        tax_quote["tax_included"],
        json.dumps(tax_quote),
        tenant,
        sid,
    )
    if tax_quote.get("promotion"):
        promotion = tax_quote["promotion"]
        await c.execute(
            "UPDATE sales SET promotion_snapshot=$1 WHERE tenant=$2 AND id=$3",
            json.dumps(promotion),
            tenant,
            sid,
        )
        await c.execute(
            "INSERT INTO promotion_redemptions(tenant,promotion,sale,discount,customer) VALUES($1,$2,$3,$4,$5)",
            tenant,
            promotion["id"],
            sid,
            discount,
            customer_id,
        )
    if credit_amount:
        await credit.create_receivable(
            c, tenant, customer_id, sid, credit_amount, due, u["email"], inv
        )
    await c.execute(
        "UPDATE sales SET prescription_reference=$1 WHERE tenant=$2 AND id=$3",
        prescription_reference,
        tenant,
        sid,
    )
    till = await c.fetchval(
        "SELECT id FROM till_sessions WHERE tenant=$1 AND actor=$2 AND status='open'",
        tenant,
        u["id"],
    )
    await c.execute(
        "UPDATE sales SET cash_amount=$1 WHERE tenant=$2 AND id=$3",
        cash_amount,
        tenant,
        sid,
    )
    for part in parts:
        await c.execute(
            "INSERT INTO sale_tenders(id,tenant,sale,method_id,method_name,method_name_ur,is_cash,amount,reference) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            uid(),
            tenant,
            sid,
            part["method_id"],
            part["name"],
            part["name_ur"],
            part["is_cash"],
            part["amount"],
            part["reference"],
        )
    if till:
        await c.execute(
            "UPDATE sales SET till_session=$1 WHERE tenant=$2 AND id=$3",
            till,
            tenant,
            sid,
        )
    for p in products:
        await c.execute(
            "INSERT INTO sale_items(id,sale,tenant,product,name,sku,quantity,price,cost,unit_name,line_total) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
            uid(),
            sid,
            tenant,
            p["id"],
            p["name"],
            p["sku"],
            p["quantity"],
            p["price"],
            p["cost"],
            p["unit_name"],
            p["line_total"],
        )
        await c.execute(
            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor) VALUES($1,$2,$3,$4,'SALE',$5,$6)",
            uid(),
            tenant,
            p["id"],
            -p["quantity"],
            inv,
            u["email"],
        )
    if held_id:
        await c.execute(
            "UPDATE held_bills SET consumed_sale=$1 WHERE tenant=$2 AND id=$3",
            sid,
            tenant,
            held_id,
        )
    await audit(
        c, tenant, u, "Sale completed", {"id": sid, "invoice": inv, "total": total}
    )
    return {
        "id": sid,
        "total": total,
        "invoice_number": inv,
        "cash_received": tendered if cash_amount else 0,
        "cash_amount": cash_amount,
        "change": tendered - cash_amount if cash_amount else 0,
        "credit_amount": credit_amount,
        "paid_now": paid_now,
    }


async def return_sale(c, u, b, t=None):
    tenant = b.get("tenant", "")
    sid = clean(b.get("id"), "Sale ID", 100)
    reason = clean(b.get("reason"), "Reason", 500)
    sale = await c.fetchrow(
        "SELECT * FROM sales WHERE tenant=$1 AND id=$2 FOR UPDATE", tenant, sid
    )
    if not sale:
        fail("Sale not found.", 404)
    if sale["revision"]:
        fail("Use item adjustments for an invoice that has already been revised.", 409)
    if sale["status"] == "returned":
        return {"ok": True}
    from .transaction_approvals import consume
    await consume(c, u, tenant, "return", b, sid)
    reason_id = b.get("reason_id") or None
    if reason_id:
        await lookup(c, tenant, reason_id, "return_reason")
    await c.execute(
        "UPDATE sales SET return_reason_id=$1 WHERE tenant=$2 AND id=$3",
        reason_id,
        tenant,
        sid,
    )
    refund_due = (
        await credit.reverse_credit_sale(c, u, tenant, sale)
        if sale["credit_amount"]
        else sale["total"]
    )
    for item in await c.fetch(
        "SELECT * FROM sale_items WHERE tenant=$1 AND sale=$2", tenant, sid
    ):
        source = await c.fetchval(
            "SELECT m.id FROM movements m WHERE m.tenant=$1 AND m.product=$2 AND m.type='SALE' AND m.notes=$3 AND EXISTS(SELECT 1 FROM stock_batch_allocations a WHERE a.movement=m.id) LIMIT 1",
            tenant,
            item["product"],
            sale["invoice_number"],
        )
        await c.execute(
            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,source_movement) VALUES($1,$2,$3,$4,'RETURN',$5,$6,$7)",
            "return-" + item["id"],
            tenant,
            item["product"],
            item["quantity"],
            reason,
            u["email"],
            source,
        )
    await c.execute(
        "UPDATE sales SET status='returned' WHERE tenant=$1 AND id=$2", tenant, sid
    )
    await audit(
        c,
        tenant,
        u,
        "Sale returned",
        {"id": sid, "reason": reason, "external_refund_due": refund_due},
    )
    return {"ok": True, "external_refund_due": refund_due}
