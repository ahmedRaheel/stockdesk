"""Inventory commands. Caller owns authorization and transaction scope."""

from ..rules import clean, number, fail
from ..service import audit


async def adjust_stock(c, u, b, t=None):
    tenant = b.get("tenant", "")
    pid = clean(b.get("product"), "Product ID", 100)
    kind = b.get("type")
    quantity = number(b.get("quantity"), "Quantity", 1, 1000000000)
    notes = clean(b.get("notes"), "Reason", 500)
    request = clean(b.get("request"), "Request ID", 100)
    if kind not in ["IN", "OUT"]:
        fail("Invalid movement type.")
    quantity = quantity if kind == "IN" else -quantity
    prior = await c.fetchrow(
        "SELECT * FROM movements WHERE id=$1 AND tenant=$2", request, tenant
    )
    if prior:
        if (
            prior["product"] != pid
            or prior["quantity"] != quantity
            or prior["notes"] != notes
        ):
            fail("Submission ID already used.")
        return {"ok": True}
    p = await c.fetchrow(
        "SELECT * FROM products WHERE id=$1 AND tenant=$2 AND active=true", pid, tenant
    )
    if not p:
        fail("Active product not found.", 404)
    if p["stock"] + quantity < 0:
        fail(f"Insufficient stock. Available: {p['stock']}.")
    await c.execute(
        "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
        request,
        tenant,
        pid,
        quantity,
        kind,
        notes,
        u["email"],
    )
    await audit(
        c,
        tenant,
        u,
        "Stock adjusted",
        {"product": pid, "quantity": quantity, "notes": notes},
    )
    return {"ok": True}
