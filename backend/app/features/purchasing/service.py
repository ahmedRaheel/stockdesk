"""Transaction boundary is owned by the HTTP caller.

Tenant locking follows checkout's lock order. Every receipt updates purchase lines,
stock ledger, receipt deduplication record and audit entry in the same transaction.
Purchase costs are retained on the PO; receiving does not silently revalue stock.
"""

import json
from decimal import Decimal, ROUND_HALF_UP
from ... import service
from ...rules import fail


def signature(payload):
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def unique_lines(lines):
    if len({line["product"] for line in lines}) != len(lines):
        fail("A product may appear only once per submission.")


async def add_supplier(connection, user, tenant, payload):
    await service.authorize(connection, user, tenant, "stock", lock=True)
    supplier_id = service.uid()
    await connection.execute(
        "INSERT INTO suppliers(id,tenant,name,contact,lead_days) VALUES($1,$2,$3,$4,$5)",
        supplier_id,
        tenant,
        payload["name"],
        payload["contact"],
        payload["lead_days"],
    )
    await service.audit(
        connection, tenant, user, "Supplier created", {"id": supplier_id}
    )
    return {"id": supplier_id}


async def create_order(connection, user, tenant, payload):
    await service.authorize(connection, user, tenant, "stock", lock=True)
    unique_lines(payload["lines"])
    # Keep pre-tier request signatures replayable after upgrading.
    payload = {
        **payload,
        "lines": [
            {k: v for k, v in line.items() if k != "quote" or v is not None}
            for line in payload["lines"]
        ],
    }
    fingerprint = signature(payload)
    existing = await connection.fetchrow(
        "SELECT id,signature FROM purchase_orders WHERE tenant=$1 AND request=$2",
        tenant,
        payload["request"],
    )
    if existing:
        if existing["signature"] != fingerprint:
            fail("Request ID has already been used with different purchase data.", 409)
        return {"id": existing["id"]}
    supplier = await connection.fetchrow(
        "SELECT * FROM suppliers WHERE tenant=$1 AND id=$2", tenant, payload["supplier"]
    )
    if not supplier:
        fail("Supplier not found.", 404)
    policy = await connection.fetchrow(
        "SELECT * FROM purchasing_policies WHERE tenant=$1", tenant
    )
    total = sum(
        int(
            (Decimal(str(l["quantity"])) * l["unit_cost"]).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        for l in payload["lines"]
    )
    if total > 100_000_000_000:
        fail("Purchase order value exceeds the allowed limit.")
    approval_required = bool(
        policy and policy["enabled"] and total >= policy["threshold"]
    )
    order_id = service.uid()
    await connection.execute(
        "INSERT INTO purchase_orders(id,tenant,supplier,request,signature,reference,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
        order_id,
        tenant,
        payload["supplier"],
        payload["request"],
        fingerprint,
        payload["reference"],
        user["email"],
    )
    await connection.execute(
        "UPDATE purchase_orders SET status=$1,approval_required=$2,approval_threshold=$3,order_total=$4,lead_days_snapshot=$5 WHERE tenant=$6 AND id=$7",
        "pending_approval" if approval_required else "open",
        approval_required,
        policy["threshold"] if policy and policy["enabled"] else None,
        total,
        supplier["lead_days"],
        tenant,
        order_id,
    )
    for line in payload["lines"]:
        from ..reference import lookup

        unit_id = await connection.fetchval(
            "SELECT unit_id FROM products WHERE tenant=$1 AND id=$2",
            tenant,
            line["product"],
        )
        unit = await lookup(connection, tenant, unit_id, "unit", allow_inactive=True)
        if not unit["fractional"] and line["quantity"] != int(line["quantity"]):
            fail("This product requires whole quantities.")
        if not await connection.fetchval(
            "SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND active=true",
            tenant,
            line["product"],
        ):
            fail("An active product could not be found.", 404)
        from ..supplier_prices import selected_quote

        snapshot = await selected_quote(connection, tenant, payload["supplier"], line)
        await connection.execute(
            "INSERT INTO purchase_lines(tenant,purchase,product,quantity,unit_cost,quote_snapshot) VALUES($1,$2,$3,$4,$5,$6::jsonb)",
            tenant,
            order_id,
            line["product"],
            line["quantity"],
            line["unit_cost"],
            json.dumps(snapshot, default=str) if snapshot else None,
        )
    await service.audit(
        connection, tenant, user, "Purchase order created", {"id": order_id}
    )
    return {"id": order_id}


async def receive_order(connection, user, tenant, order_id, payload):
    await service.authorize(connection, user, tenant, "stock", lock=True)
    unique_lines(payload["lines"])
    fingerprint = signature({"purchase": order_id, **payload})
    prior = await connection.fetchrow(
        "SELECT id,signature FROM purchase_receipts WHERE tenant=$1 AND request=$2",
        tenant,
        payload["request"],
    )
    if prior:
        if prior["signature"] != fingerprint:
            fail("Request ID has already been used with different receipt data.", 409)
        return {"id": prior["id"]}
    order = await connection.fetchrow(
        "SELECT * FROM purchase_orders WHERE tenant=$1 AND id=$2 FOR UPDATE",
        tenant,
        order_id,
    )
    if not order:
        fail("Purchase order not found.", 404)
    if order["status"] not in ("open", "partial"):
        fail("Only open or partially received orders can receive stock.", 409)
    receipt_id = service.uid()
    sources = []
    for line in payload["lines"]:
        from ..reference import lookup

        unit_id = await connection.fetchval(
            "SELECT unit_id FROM products WHERE tenant=$1 AND id=$2",
            tenant,
            line["product"],
        )
        unit = await lookup(connection, tenant, unit_id, "unit", allow_inactive=True)
        if not unit["fractional"] and line["quantity"] != int(line["quantity"]):
            fail("This product requires whole quantities.")
        pending = await connection.fetchrow(
            "SELECT l.*,p.active FROM purchase_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product WHERE l.tenant=$1 AND l.purchase=$2 AND l.product=$3 FOR UPDATE OF l,p",
            tenant,
            order_id,
            line["product"],
        )
        if not pending or not pending["active"]:
            fail("The product is not active on this purchase order.", 409)
        if line["quantity"] > pending["quantity"] - pending["received"]:
            fail("Received quantity exceeds the outstanding order quantity.", 409)
        await connection.execute(
            "UPDATE purchase_lines SET received=received+$1 WHERE tenant=$2 AND purchase=$3 AND product=$4",
            line["quantity"],
            tenant,
            order_id,
            line["product"],
        )
        movement_id = service.uid()
        sources.append((movement_id, line["product"], line["quantity"]))
        await connection.execute(
            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,lot,expires) VALUES($1,$2,$3,$4,'IN',$5,$6,$7,$8)",
            movement_id,
            tenant,
            line["product"],
            line["quantity"],
            f"Purchase {order_id}; receipt {receipt_id}",
            user["email"],
            line.get("lot", ""),
            line.get("expires"),
        )
    remaining = await connection.fetchval(
        "SELECT SUM(quantity-received) FROM purchase_lines WHERE tenant=$1 AND purchase=$2",
        tenant,
        order_id,
    )
    await connection.execute(
        "UPDATE purchase_orders SET status=$1 WHERE tenant=$2 AND id=$3",
        "partial" if remaining else "received",
        tenant,
        order_id,
    )
    await connection.execute(
        "INSERT INTO purchase_receipts(id,tenant,purchase,request,signature,actor) VALUES($1,$2,$3,$4,$5,$6)",
        receipt_id,
        tenant,
        order_id,
        payload["request"],
        fingerprint,
        user["email"],
    )
    for movement_id, product, quantity in sources:
        batch = await connection.fetchval(
            "SELECT batch FROM stock_batch_allocations WHERE tenant=$1 AND movement=$2",
            tenant,
            movement_id,
        )
        await connection.execute(
            "INSERT INTO purchase_receipt_sources(movement,tenant,purchase,receipt,product,batch,quantity) VALUES($1,$2,$3,$4,$5,$6,$7)",
            movement_id,
            tenant,
            order_id,
            receipt_id,
            product,
            batch,
            quantity,
        )
    await service.audit(
        connection,
        tenant,
        user,
        "Purchase received",
        {"purchase": order_id, "receipt": receipt_id, "lines": payload["lines"]},
    )
    return {"id": receipt_id}


async def cancel_order(connection, user, tenant, order_id):
    await service.authorize(connection, user, tenant, "stock", lock=True)
    order = await connection.fetchrow(
        "SELECT status FROM purchase_orders WHERE tenant=$1 AND id=$2 FOR UPDATE",
        tenant,
        order_id,
    )
    if not order:
        fail("Purchase order not found.", 404)
    if order["status"] in ("received", "rejected"):
        fail("Received or rejected orders cannot be cancelled.", 409)
    if order["status"] != "cancelled":
        await connection.execute(
            "UPDATE purchase_orders SET status='cancelled' WHERE tenant=$1 AND id=$2",
            tenant,
            order_id,
        )
        await service.audit(
            connection, tenant, user, "Purchase remainder cancelled", {"id": order_id}
        )
    return {"ok": True}
