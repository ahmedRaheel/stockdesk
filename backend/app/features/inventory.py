"""Inventory commands. Caller owns authorization and transaction scope."""

from ..rules import clean, number, fail, quantity as parse_quantity
from ..service import audit


async def adjust_stock(c, u, b, t=None):
    tenant = b.get("tenant", "")
    pid = clean(b.get("product"), "Product ID", 100)
    kind = b.get("type")
    quantity = parse_quantity(b.get("quantity"), "Quantity", minimum=0.001)
    notes = clean(b.get("notes"), "Reason", 500)
    request = clean(b.get("request"), "Request ID", 100)
    from datetime import date

    lot = clean(b.get("lot", ""), "Batch", 80, True)
    expires = b.get("expires")
    if isinstance(expires, str):
        try:
            expires = date.fromisoformat(expires)
        except ValueError:
            fail("Invalid expiry date.")
    batch_id = b.get("batch_id") or None
    reason_id = b.get("reason_id") or None
    if reason_id:
        from .reference import lookup

        await lookup(c, tenant, reason_id, "adjustment_reason")
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
            or prior["lot"] != lot
            or prior["expires"] != expires
            or prior["batch_id"] != batch_id
            or prior["reason_id"] != reason_id
        ):
            fail("Submission ID already used.")
        return {"ok": True}
    if kind == "IN" and batch_id:
        fail("For receipts supply lot and expiry, not an existing batch ID.")
    p = await c.fetchrow(
        "SELECT * FROM products WHERE id=$1 AND tenant=$2 AND active=true", pid, tenant
    )
    if not p:
        fail("Active product not found.", 404)
    from .reference import lookup

    unit = await lookup(c, tenant, p["unit_id"], "unit", allow_inactive=True)
    if not unit["fractional"] and quantity != quantity.to_integral_value():
        fail("This unit requires whole quantities.")
    if kind == "IN" and p["expiry_required"] and (not lot or not expires):
        fail("Batch number and expiry date are required.")
    if p["stock"] + quantity < 0:
        fail(f"Insufficient stock. Available: {p['stock']}.")
    await c.execute(
        "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,lot,expires,batch_id,reason_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        request,
        tenant,
        pid,
        quantity,
        kind,
        notes,
        u["email"],
        lot,
        expires,
        batch_id,
        reason_id,
    )
    await audit(
        c,
        tenant,
        u,
        "Stock adjusted",
        {"product": pid, "quantity": quantity, "notes": notes, "reason_id": reason_id},
    )
    return {"ok": True}
