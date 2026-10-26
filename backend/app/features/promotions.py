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
    reward_details = {}
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
    elif kind == "cross_bogo":
        reward_id = rule["reward_product"]
        buy_id = next(c["product"] for c in components if c["product"] != reward_id)
        buy, reward = by_id.get(buy_id), by_id.get(reward_id)
        for item in (buy, reward):
            if (
                item
                and Decimal(item["quantity"])
                != Decimal(item["quantity"]).to_integral_value()
            ):
                fail("Cross-product BOGO requires whole product quantities.")
        groups = int(Decimal(buy["quantity"]) // rule["buy_quantity"]) if buy else 0
        free = (
            min(int(Decimal(reward["quantity"])), groups * rule["free_quantity"])
            if reward
            else 0
        )
        discount = line_amount(reward["price"], Decimal(free)) if reward else 0
        weights = [p["line_total"] if p["id"] == reward_id else 0 for p in products]
        reward_details = dict(
            buy_product=buy_id,
            reward_product=reward_id,
            buy_quantity=rule["buy_quantity"],
            free_quantity=rule["free_quantity"],
            reward_units=free,
            return_policy="paired_cross_bogo",
        )
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
        **reward_details,
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


async def resolve_single(c, tenant, code, products, manual_discount, customer_id=None):
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
    customer_details = {}
    if rule["per_customer_limit"] is not None:
        if not customer_id:
            fail("Select a registered customer for this promotion.")
        if not await c.fetchval(
            "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active=true",
            tenant,
            customer_id,
        ):
            fail("Choose an active customer from this business.")
        customer_used = await c.fetchval(
            "SELECT count(*) FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2 AND customer=$3",
            tenant,
            rule["id"],
            customer_id,
        )
        if customer_used >= rule["per_customer_limit"]:
            fail("This customer has reached the promotion redemption limit.", 409)
        customer_details = dict(
            customer_id=customer_id, per_customer_limit=rule["per_customer_limit"]
        )
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
    return {
        **evaluate(
            rule, components, products, datetime.now(ZoneInfo("Asia/Karachi")), used
        ),
        **customer_details,
    }


async def automatic_candidates(c, tenant, products, customer_id=None):
    """Bounded eligible offers; caller compares final tax-inclusive totals."""
    from fastapi import HTTPException

    rules = await c.fetch(
        "SELECT p.*,(SELECT count(*) FROM promotion_redemptions r WHERE r.tenant=p.tenant AND r.promotion=p.id) used,(SELECT count(*) FROM promotion_redemptions r WHERE r.tenant=p.tenant AND r.promotion=p.id AND r.customer=$2) customer_used FROM promotions p WHERE tenant=$1 AND active AND automatic ORDER BY code,id LIMIT 101",
        tenant,
        customer_id,
    )
    if len(rules) > 100:
        fail(
            "At most 100 active automatic promotions are allowed. Disable an existing offer first.",
            409,
        )
    components = await c.fetch(
        "SELECT promotion,product,quantity FROM promotion_items WHERE tenant=$1 AND promotion=ANY($2::text[]) ORDER BY product",
        tenant,
        [r["id"] for r in rules],
    )
    active_customer = bool(customer_id) and await c.fetchval(
        "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active=true",
        tenant,
        customer_id,
    )
    now = datetime.now(ZoneInfo("Asia/Karachi"))
    candidates = []
    for rule in rules:
        details = {}
        if rule["per_customer_limit"] is not None:
            if (
                not active_customer
                or rule["customer_used"] >= rule["per_customer_limit"]
            ):
                continue
            details = dict(
                customer_id=customer_id, per_customer_limit=rule["per_customer_limit"]
            )
        try:
            result = evaluate(
                rule,
                [x for x in components if x["promotion"] == rule["id"]],
                products,
                now,
                rule["used"],
            )
        except HTTPException as exc:
            if exc.status_code not in (400, 409):
                raise
            continue
        candidates.append({**result, **details})
    return candidates


def return_groups(promotion):
    """Merge overlapping cross-BOGO pairs; unrelated pairs stay independent."""
    offers = promotion.get("offers", [promotion])
    groups = []
    for offer in offers:
        if offer.get("kind") != "cross_bogo":
            continue
        group = {offer["buy_product"], offer["reward_product"]}
        changed = True
        while changed:
            changed = False
            for existing in groups[:]:
                if existing & group:
                    group |= existing
                    groups.remove(existing)
                    changed = True
        groups.append(group)
    return [sorted(g) for g in groups]


async def resolve(c, tenant, code, products, manual_discount, customer_id=None):
    code = clean(code or "", "Promotion codes", 240, True).upper()
    if not code or "," not in code:
        return await resolve_single(
            c, tenant, code, products, manual_discount, customer_id
        )
    codes = [x.strip() for x in code.split(",")]
    if (
        not 2 <= len(codes) <= 5
        or any(not x or len(x) > 40 for x in codes)
        or len(set(codes)) != len(codes)
    ):
        fail("Enter two to five distinct promotion codes separated by commas.")
    if manual_discount:
        fail("Manual and promotional discounts cannot be combined.")
    rules = await c.fetch(
        "SELECT * FROM promotions WHERE tenant=$1 AND code=ANY($2::text[])",
        tenant,
        codes,
    )
    if len(rules) != len(codes):
        fail("Promotion code not found.", 404)
    if any(not rule["stackable"] for rule in rules):
        fail("Every combined offer must allow stacking.", 409)
    # Stable application order: product offers, fixed invoice discounts, then
    # sequential percentages. Code order resolves ties independent of typing order.
    priority = {"bogo": 0, "cross_bogo": 0, "bundle": 0, "fixed": 1, "percentage": 2}
    rules = sorted(rules, key=lambda rule: (priority[rule["kind"]], rule["code"]))
    remaining = [p["line_total"] for p in products]
    offers = []
    for rule in rules:
        offer = await resolve_single(c, tenant, rule["code"], products, 0, customer_id)
        if rule["kind"] == "percentage":
            amount = (sum(remaining) * rule["value"] + 5000) // 10000
            if rule["maximum_discount"] is not None:
                amount = min(amount, rule["maximum_discount"])
            deductions = allocate_discount(remaining, min(amount, sum(remaining)))
        elif rule["kind"] == "fixed":
            deductions = allocate_discount(
                remaining, min(offer["discount"], sum(remaining))
            )
        else:
            deductions = [
                min(left, line["discount"])
                for left, line in zip(remaining, offer["line_discounts"])
            ]
        amount = sum(deductions)
        if not amount:
            fail(
                "A combined offer adds no further discount. Remove it and review again.",
                409,
            )
        remaining = [left - d for left, d in zip(remaining, deductions)]
        offers.append(
            {
                **offer,
                "discount": amount,
                "line_discounts": [
                    {"product": p["id"], "discount": d}
                    for p, d in zip(products, deductions)
                ],
            }
        )
    deductions = [p["line_total"] - left for p, left in zip(products, remaining)]
    return {
        "kind": "stack",
        "code": " + ".join(x["code"] for x in offers),
        "name": "Combined offers",
        "name_ur": "مشترکہ پیشکشیں",
        "discount": sum(deductions),
        "offers": offers,
        "application_policy": "product_then_fixed_then_percentage",
        "line_discounts": [
            {"product": p["id"], "discount": d} for p, d in zip(products, deductions)
        ],
    }
