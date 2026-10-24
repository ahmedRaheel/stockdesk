import pytest
from fastapi import HTTPException
from app.rules import number, cart_items, totals, require_permission, password


def test_integer_money_rounding():
    assert totals(10000, 1000, 1800) == (1620, 10620)
    assert totals(1, 0, 5000) == (1, 2)


@pytest.mark.parametrize("v", [True, 1.5, -1, "4", None])
def test_quantity_validation(v):
    with pytest.raises(HTTPException):
        number(v)


def test_no_duplicate_cart():
    with pytest.raises(HTTPException):
        cart_items([{"id": "x", "quantity": 1}, {"id": "x", "quantity": 2}])


def test_roles():
    require_permission("Cashier", "sale")
    with pytest.raises(HTTPException):
        require_permission("Cashier", "team")
    with pytest.raises(HTTPException):
        require_permission("Stock Manager", "sale")


def test_discount_cannot_exceed_subtotal():
    with pytest.raises(HTTPException):
        totals(100, 101, 0)


def test_password_length():
    with pytest.raises(HTTPException):
        password("short")
