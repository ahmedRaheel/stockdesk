from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from app.features.reporting import analyze


def test_report_net_tax_attribution_frozen_cost_and_groups():
    end = date(2026, 10, 23)
    products = [
        dict(
            id="a",
            name="Tax included",
            sku="A",
            category="Food",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        dict(
            id="b",
            name="Exempt",
            sku="B",
            category="General",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    sale = dict(
        id="s",
        actor="cashier",
        discount=2180,
        tax=1620,
        tax_included=1620,
        tax_snapshot={
            "lines": [
                {"product": "a", "inclusive": True, "tax": 1620},
                {"product": "b", "inclusive": False, "tax": 0},
            ]
        },
        day=end,
        hour=15,
    )
    items = [
        dict(sale="s", product="a", quantity=Decimal("1"), line_total=11800, cost=5000),
        dict(sale="s", product="b", quantity=Decimal("1"), line_total=10000, cost=8000),
    ]
    report = analyze([sale], items, products, 30, end)
    assert report["summary"] == dict(
        net_sales=18000, cost=13000, profit=5000, tax=1620, invoices=1
    )
    assert {p["id"]: p["net_sales"] for p in report["products"]} == {
        "a": 9000,
        "b": 9000,
    }
    assert report["hours"][15]["net_sales"] == 18000
    assert report["cashiers"][0]["profit"] == 5000
    assert report["products"][0]["xyz"] == "Z"


def test_report_xyz_regular_demand_and_no_history():
    end = date(2026, 10, 23)
    sales = []
    items = []
    products = [
        dict(
            id="a",
            name="Regular",
            sku="A",
            category="Food",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        dict(
            id="b",
            name="New",
            sku="B",
            category="Food",
            created=datetime(2026, 10, 22, tzinfo=timezone.utc),
        ),
    ]
    for i in range(30):
        sales.append(
            dict(
                id=str(i),
                actor="c",
                discount=0,
                tax=0,
                tax_included=0,
                day=end - timedelta(days=i),
                hour=10,
            )
        )
        items.append(
            dict(
                sale=str(i), product="a", quantity=Decimal("2"), line_total=200, cost=50
            )
        )
    r = analyze(sales, items, products, 30, end)
    assert r["products"][0]["xyz"] == "X" and r["products"][0]["cv"] == 0
    assert r["products"][1]["xyz"] == "Insufficient history"
