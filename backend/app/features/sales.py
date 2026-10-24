"""Sales commands. Caller owns authorization and transaction scope."""

import json
from ..rules import clean, number, cart_items, totals, fail
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
    signature = json.dumps(
        {
            "items": cart,
            "customer": customer,
            "payment": payment,
            "discount": discount,
            "tax_bps": tax_bps,
            "expected": expected,
            "tendered": tendered,
        },
        sort_keys=True,
    )
    prior = await c.fetchrow(
        "SELECT * FROM sales WHERE tenant=$1 AND request=$2", tenant, request
    )
    if prior:
        if prior["signature"] != signature:
            fail("Submission ID already used for different data.")
        return {
            "id": prior["id"],
            "total": prior["total"],
            "invoice_number": prior["invoice_number"],
        }
    products = []
    for item in cart:
        p = await c.fetchrow(
            "SELECT * FROM products WHERE tenant=$1 AND id=$2 AND active=true FOR UPDATE",
            tenant,
            item["id"],
        )
        if not p:
            fail("A product is no longer available.")
        if p["stock"] < item["quantity"]:
            fail(f"Insufficient stock for {p['name']}. Available: {p['stock']}.")
        products.append({**dict(p), "quantity": item["quantity"]})
    subtotal = sum((p["price"] * p["quantity"] for p in products))
    number(subtotal, "Subtotal")
    tax, total = totals(subtotal, discount, tax_bps)
    if total != expected:
        fail("Prices changed. Refresh and review the cart total.")
    if payment == "cash" and tendered < total:
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
    for p in products:
        await c.execute(
            "INSERT INTO sale_items(id,sale,tenant,product,name,sku,quantity,price,cost) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            uid(),
            sid,
            tenant,
            p["id"],
            p["name"],
            p["sku"],
            p["quantity"],
            p["price"],
            p["cost"],
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
    await audit(
        c, tenant, u, "Sale completed", {"id": sid, "invoice": inv, "total": total}
    )
    return {
        "id": sid,
        "total": total,
        "invoice_number": inv,
        "change": tendered - total if payment == "cash" else 0,
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
    if sale["status"] == "returned":
        return {"ok": True}
    for item in await c.fetch(
        "SELECT * FROM sale_items WHERE tenant=$1 AND sale=$2", tenant, sid
    ):
        await c.execute(
            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor) VALUES($1,$2,$3,$4,'RETURN',$5,$6)",
            "return-" + item["id"],
            tenant,
            item["product"],
            item["quantity"],
            reason,
            u["email"],
        )
    await c.execute(
        "UPDATE sales SET status='returned' WHERE tenant=$1 AND id=$2", tenant, sid
    )
    await audit(c, tenant, u, "Sale returned", {"id": sid, "reason": reason})
    return {"ok": True}
