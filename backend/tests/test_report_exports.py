from datetime import date
from decimal import Decimal
from io import BytesIO
import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from app.features.turnover import metrics
from app.features.report_exports import xlsx_export, pdf_export


def sample():
    return dict(
        business="Test shop",
        currency="PKR",
        start=date(2026, 10, 1),
        end=date(2026, 10, 7),
        products=[
            dict(
                sku="0012",
                name='=HYPERLINK("https://invalid")',
                units=Decimal("1.25"),
                net_sales=125050,
                cost=100000,
                profit=25050,
                margin_pct=20.032,
                abc="A",
                xyz="X",
                cv=0.1,
                observed_days=7,
            )
        ],
    )


def test_turnover_fractional_zero_stock_returns_and_exact_daily_average():
    row = dict(
        id="p",
        sku="P",
        name="Product",
        unit="kg",
        opening=Decimal("10"),
        closing=Decimal("8"),
        stock_days=Decimal("68"),
        sold=Decimal("2"),
        returned=0,
    )
    m = metrics([row], 7)[0]
    assert m["average_stock"] == Decimal("9.714286")
    assert m["turnover"] == Decimal(".2059") and m["days_per_turn"] == 34
    negative = metrics([{**row, "returned": 3}], 7)[0]
    assert negative["turnover"] < 0 and negative["days_per_turn"] is None
    empty = metrics(
        [{**row, "opening": 0, "closing": 0, "stock_days": 0, "sold": 0}], 7
    )[0]
    assert empty["turnover"] is None and empty["days_per_turn"] is None
    with pytest.raises(HTTPException):
        metrics([{**row, "closing": -1}], 7)


def test_excel_safe_text_numeric_money_and_metadata():
    data = sample()
    raw = xlsx_export("products", data)
    w = load_workbook(BytesIO(raw), data_only=False)
    s = w.active
    assert s["A5"].value == "0012" and s["A5"].data_type == "s"
    assert s["B5"].value == data["products"][0]["name"] and s["B5"].data_type == "s"
    assert s["D5"].value == 1250.5 and s["D5"].data_type == "n"
    assert s.freeze_panes == "A5" and s.auto_filter.ref == "A4:K5"
    assert "PKR" in s["A2"].value
    assert not any(c.data_type == "f" for row in s for c in row)
    w.close()
    assert pdf_export("products", data).startswith(b"%PDF")
    data["products"] *= 501
    with pytest.raises(HTTPException) as e:
        pdf_export("products", data)
    assert e.value.status_code == 422
    data["products"] *= 20
    with pytest.raises(HTTPException):
        xlsx_export("products", data)
