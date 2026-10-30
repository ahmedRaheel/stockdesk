"""Validate explicitly selected quantity quotes inside the locked PO transaction."""

from datetime import datetime
from zoneinfo import ZoneInfo
from ..rules import fail


async def selected_quote(c, tenant, supplier, line):
    selection = line.get("quote")
    if not selection:
        return None
    offer = await c.fetchrow(
        "SELECT * FROM supplier_offers WHERE tenant=$1 AND id=$2 AND supplier=$3 AND product=$4",
        tenant,
        selection["id"],
        supplier,
        line["product"],
    )
    if not offer:
        fail("Supplier quote not found for this order line.", 404)
    today = datetime.now(ZoneInfo("Asia/Karachi")).date()
    if (
        offer["version"] != selection["version"]
        or not offer["active"]
        or offer["valid_from"] > today
        or (offer["valid_until"] and offer["valid_until"] < today)
        or line["quantity"] < offer["minimum_quantity"]
    ):
        fail(
            "Selected quote changed or is no longer eligible. Compare prices again.",
            409,
        )
    tier = await c.fetchrow(
        "SELECT minimum_quantity,unit_cost FROM supplier_offer_tiers WHERE tenant=$1 AND offer=$2 AND minimum_quantity<=$3 ORDER BY minimum_quantity DESC LIMIT 1",
        tenant,
        offer["id"],
        line["quantity"],
    )
    applied = tier or offer
    if line["unit_cost"] != applied["unit_cost"]:
        fail(
            "Selected quote price does not match this quantity. Compare prices again.",
            409,
        )
    return {
        "id": offer["id"],
        "version": offer["version"],
        "minimum_quantity": applied["minimum_quantity"],
        "unit_cost": applied["unit_cost"],
        "valid_from": offer["valid_from"],
        "valid_until": offer["valid_until"],
        "lead_days": offer["lead_days"],
        "notes": offer["notes"],
        "as_of": today,
    }
