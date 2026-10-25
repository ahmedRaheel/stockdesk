"""Deterministic promotional discounts. Caller owns tenant write lock on checkout."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from ..rules import fail, clean, line_amount
from .taxation import allocate_discount


def evaluate(rule, components, products, now, used=0):
    local = now.astimezone(ZoneInfo("Asia/Karachi"))
    day = local.date()
    minute = local.hour * 60 + local.minute
    start, end = rule["starts_minute"], rule["ends_minute"]
    if start is not None:
        if start < end:
            eligible = start <= minute < end
        elif start > end:
            eligible = minute >= start or minute < end
            if minute < end:
                day -= timedelta(days=1)
        else:
            eligible = False
        if not eligible:
            fail("Promotion is outside its daily time window.", 409)
    # Overnight hours inherit the weekday and effective date of the window's start.
    if (
        not rule["active"]
        or (rule["starts_on"] and day < rule["starts_on"])
        or (rule["ends_on"] and day > rule["ends_on"])
    ):
        fail("Promotion is inactive or outside its effective dates.", 409)
    if day.weekday() not in rule.get("weekdays", list(range(7))):
        fail("Promotion is not available on this weekday.", 409)
    if rule["usage_limit"] is not None and used >= rule["usage_limit"]:
        fail("Promotion usage limit has been reached.", 409)
    subtotal = sum(p["line_total"] for p in products)
    if subtotal < rule["minimum_subtotal"]:
        fail("Cart does not meet the promotion minimum subtotal.")
    weights = [p["line_total"] for p in products]
    by_id = {p["id"]: p for p in products}
    kind = rule["kind"]
    if kind == "fixed":
        discount = min(rule["value"], subtotal)
    elif kind == "percentage":
        discount = (subtotal * rule["value"] + 5000) // 10000
    elif kind == "bogo":
        c = components[0]
        p = by_id.get(c["product"])
        groups = (
            int(
                Decimal(p["quantity"]) // (rule["buy_quantity"] + rule["free_quantity"])
            )
            if p
            else 0
        )
        discount = (
            line_amount(p["price"], Decimal(groups * rule["free_quantity"])) if p else 0
        )
        weights = [p["line_total"] if p["id"] == c["product"] else 0 for p in products]
    else:  # Bundle: all components must be present in the cart; no implicit stock lines.
        groups = min(
            (
                int(Decimal(by_id[c["product"]]["quantity"]) // Decimal(c["quantity"]))
                if c["product"] in by_id
                else 0
            )
            for c in components
        )
        matched = {
            c["product"]: line_amount(
                by_id[c["product"]]["price"], Decimal(c["quantity"]) * groups
            )
            for c in components
            if c["product"] in by_id
        }
        discount = max(0, sum(matched.values()) - rule["value"] * groups)
        weights = [matched.get(p["id"], 0) for p in products]
    if rule["maximum_discount"] is not None:
        discount = min(discount, rule["maximum_discount"])
    if discount <= 0:
        fail("Cart does not qualify for a positive promotion discount.")
    # Price/quantity rounding cannot discount a line below zero.
    weights = [min(w, p["line_total"]) for w, p in zip(weights, products)]
    discount = min(discount, sum(weights))
    deductions = allocate_discount(weights, discount)
    return dict(
        id=rule["id"],
        code=rule["code"],
        name=rule["name"],
        name_ur=rule["name_ur"],
        kind=kind,
        version=rule["version"],
        discount=discount,
        line_discounts=[
            dict(product=p["id"], discount=d) for p, d in zip(products, deductions)
        ],
    )


async def resolve(c, tenant, code, products, manual_discount):
    code = clean(code or "", "Promotion code", 40, True).upper()
    if not code:
        return None
    if manual_discount:
        fail("Manual and promotional discounts cannot be combined.")
    rule = await c.fetchrow(
        "SELECT * FROM promotions WHERE tenant=$1 AND code=$2", tenant, code
    )
    if not rule:
        fail("Promotion code not found.", 404)
    components = await c.fetch(
        "SELECT product,quantity FROM promotion_items WHERE tenant=$1 AND promotion=$2 ORDER BY product",
        tenant,
        rule["id"],
    )
    used = await c.fetchval(
        "SELECT COUNT(*) FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2",
        tenant,
        rule["id"],
    )
    return evaluate(
        rule, components, products, datetime.now(ZoneInfo("Asia/Karachi")), used
    )
