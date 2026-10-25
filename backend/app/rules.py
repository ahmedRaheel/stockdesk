"""Pure validation and money calculations; monetary values use integer minor units."""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fastapi import HTTPException

ROLES = {
    "Owner": {
        "promotions",
        "roles",
        "audit",
        "count_approve",
        "purchase_approve",
        "supplier_return",
        "finance",
        "credit",
        "credit_approve",
        "cost",
        "forecast",
        "read",
        "product",
        "stock",
        "sale",
        "return",
        "team",
        "settings",
    },
    "Manager": {
        "promotions",
        "count_approve",
        "purchase_approve",
        "supplier_return",
        "finance",
        "credit",
        "credit_approve",
        "cost",
        "forecast",
        "read",
        "product",
        "stock",
        "sale",
        "return",
    },
    "Cashier": {"credit", "read", "sale"},
    "Stock Manager": {"cost", "forecast", "read", "product", "stock"},
}


def fail(message, status=400):
    raise HTTPException(status, message)


class EffectiveRole(str):
    """Per-request role; never store tenant grants in the global built-in role map."""

    def __new__(cls, name, permissions):
        instance = super().__new__(cls, name)
        instance.permissions = frozenset(permissions)
        return instance


def grants(role):
    return getattr(role, "permissions", ROLES.get(role, set()))


def require_permission(role, permission):
    if permission not in grants(role):
        fail("Your role cannot perform this action.", 403)


def clean(v, label="Value", maximum=150, optional=False):
    if (
        not isinstance(v, str)
        or (not optional and not v.strip())
        or len(v.strip()) > maximum
    ):
        fail(f"{label} is required and must be at most {maximum} characters.")
    return v.strip()


def number(v, label="Number", minimum=0, maximum=100_000_000_000):
    if type(v) is not int or not minimum <= v <= maximum:
        fail(f"{label} must be a whole number between {minimum} and {maximum}.")
    return v


def email(v):
    v = clean(v, "Email", 254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v):
        fail("Enter a valid email.")
    return v


def password(v):
    if not isinstance(v, str) or not 6 <= len(v) <= 128:
        fail("Password must contain 6–128 characters.")
    return v


def boolean(v):
    if type(v) is not bool:
        fail("Expected true or false.")
    return v


def cart_items(v):
    if not isinstance(v, list) or not 1 <= len(v) <= 100:
        fail("Cart must contain 1–100 products.")
    result = []
    seen = set()
    for x in v:
        if not isinstance(x, dict):
            fail("Invalid cart item.")
        pid = clean(x.get("id"), "Product ID", 100)
        if pid in seen:
            fail("Duplicate product in cart.")
        seen.add(pid)
        result.append(
            {
                "id": pid,
                "quantity": quantity(
                    x.get("quantity"), "Quantity", Decimal("0.001"), Decimal("100000")
                ),
            }
        )
    return sorted(result, key=lambda x: x["id"])


def totals(subtotal, discount, tax_bps):
    number(discount, "Discount", 0, subtotal)
    number(tax_bps, "Tax rate", 0, 10000)
    tax = ((subtotal - discount) * tax_bps + 5000) // 10000
    return tax, subtotal - discount + tax


def quantity(
    value, label="Quantity", minimum=Decimal("0"), maximum=Decimal("1000000000")
):
    if isinstance(value, bool):
        fail(f"{label} must be a number.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label} must be a number.")
    if (
        not result.is_finite()
        or result < minimum
        or result > maximum
        or result != result.quantize(Decimal("0.001"))
    ):
        fail(f"{label} must be within range and have at most 3 decimal places.")
    return result


def line_amount(price, quantity):
    return int(
        (Decimal(price) * quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def business_date():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Karachi")).date()
