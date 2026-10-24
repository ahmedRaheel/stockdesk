"""Pure validation and money calculations; monetary values use integer minor units."""

import re
from fastapi import HTTPException

ROLES = {
    "Owner": {
        "forecast",
        "read",
        "product",
        "stock",
        "sale",
        "return",
        "team",
        "settings",
    },
    "Manager": {"forecast", "read", "product", "stock", "sale", "return"},
    "Cashier": {"read", "sale"},
    "Stock Manager": {"forecast", "read", "product", "stock"},
}


def fail(message, status=400):
    raise HTTPException(status, message)


def require_permission(role, permission):
    if permission not in ROLES.get(role, set()):
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
            {"id": pid, "quantity": number(x.get("quantity"), "Quantity", 1, 100000)}
        )
    return sorted(result, key=lambda x: x["id"])


def totals(subtotal, discount, tax_bps):
    number(discount, "Discount", 0, subtotal)
    number(tax_bps, "Tax rate", 0, 10000)
    tax = ((subtotal - discount) * tax_bps + 5000) // 10000
    return tax, subtotal - discount + tax
