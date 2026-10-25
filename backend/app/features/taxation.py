"""Deterministic tax quote shared by preview and checkout; no rates trusted from UI.

Money is integer minor units. Invoice discounts are allocated by largest remainder,
then tax rounds half up per line. Included tax is extracted, never added twice.
"""

import hashlib, json
from ..rules import fail, totals, business_date, line_amount, cart_items


def allocate_discount(amounts, discount):
    subtotal = sum(amounts)
    if discount < 0 or discount > subtotal:
        fail("Discount exceeds subtotal.")
    if not subtotal:
        return [0] * len(amounts)
    allocated = [discount * a // subtotal for a in amounts]
    remainders = [discount * a % subtotal for a in amounts]
    for i in sorted(range(len(amounts)), key=lambda i: (-remainders[i], i))[
        : discount - sum(allocated)
    ]:
        allocated[i] += 1
    return allocated


def calculate(lines, discount, mode, manual_bps=0, line_discounts=None):
    amounts = [x["line_total"] for x in lines]
    subtotal = sum(amounts)
    deductions = (
        allocate_discount(amounts, discount)
        if line_discounts is None
        else line_discounts
    )
    if (
        len(deductions) != len(amounts)
        or sum(deductions) != discount
        or any(d < 0 or d > a for d, a in zip(deductions, amounts))
    ):
        fail("Invalid promotion line discount allocation.")
    if mode == "manual":
        tax, total = totals(subtotal, discount, manual_bps)
        return dict(
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            tax_included=0,
            total=total,
            lines=[],
            mode=mode,
        )
    result = []
    tax = 0
    included = 0
    for item, deduct in zip(lines, deductions):
        base = item["line_total"] - deduct
        rate = item.get("rate_bps", 0) if mode == "configured" else 0
        inc = item.get("inclusive", False) and mode == "configured"
        denominator = 10000 + rate if inc else 10000
        value = (base * rate + denominator // 2) // denominator
        tax += value
        included += value if inc else 0
        result.append(
            dict(
                product=item["id"],
                profile_id=item.get("profile_id"),
                name=item.get("tax_name", ""),
                name_ur=item.get("tax_name_ur", ""),
                rate_bps=rate,
                inclusive=inc,
                line_total=item["line_total"],
                discount=deduct,
                tax=value,
                taxable=base - value if inc else base,
            )
        )
    return dict(
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        tax_included=included,
        total=subtotal - discount + tax - included,
        lines=result,
        mode=mode,
    )


async def quote(c, tenant, products, discount, manual_bps=0, promotion_code=""):
    from .promotions import resolve

    promotion = await resolve(c, tenant, promotion_code, products, discount)
    deductions = None
    if promotion:
        discount = promotion["discount"]
        deductions = [x["discount"] for x in promotion["line_discounts"]]
    business = await c.fetchrow(
        "SELECT tax_mode,default_tax_profile FROM tenants WHERE id=$1", tenant
    )
    mode = business["tax_mode"]
    lines = []
    today = business_date()
    for product in products:
        item = dict(product)
        pid = item.get("tax_profile_id") or business["default_tax_profile"]
        if mode == "configured" and pid:
            profile = await c.fetchrow(
                "SELECT * FROM tax_profiles WHERE tenant=$1 AND id=$2", tenant, pid
            )
            if (
                not profile
                or not profile["active"]
                or (profile["starts_on"] and today < profile["starts_on"])
                or (profile["ends_on"] and today > profile["ends_on"])
            ):
                fail(
                    "Assigned tax profile is inactive or outside its effective dates. Ask the manager to update tax settings.",
                    409,
                )
            item.update(
                profile_id=pid,
                tax_name=profile["name"],
                tax_name_ur=profile["name_ur"],
                rate_bps=profile["rate_bps"],
                inclusive=profile["inclusive"],
            )
        lines.append(item)
    result = calculate(lines, discount, mode, manual_bps, deductions)
    if promotion:
        result["promotion"] = promotion
    result["quote_token"] = hashlib.sha256(
        json.dumps(
            {
                "tenant": tenant,
                "result": result,
                "cart": [(p["id"], str(p["quantity"]), p["price"]) for p in products],
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    return result


async def preview(c, tenant, body):
    products = []
    for line in cart_items(body["items"]):
        p = await c.fetchrow(
            "SELECT * FROM products WHERE tenant=$1 AND id=$2 AND active=true",
            tenant,
            line["id"],
        )
        if not p:
            fail("Product not found.", 404)
        products.append(
            {
                **dict(p),
                "quantity": line["quantity"],
                "line_total": line_amount(p["price"], line["quantity"]),
            }
        )
    return await quote(
        c,
        tenant,
        products,
        body.get("discount", 0),
        body.get("tax_bps", 0),
        body.get("promotion_code", ""),
    )
