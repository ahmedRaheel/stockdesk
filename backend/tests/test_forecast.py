from datetime import date, timedelta
from app.forecast import analyze, window, rates

TODAY = date(2026, 10, 23)


def product(pid="p", days=90, stock=10):
    return dict(
        id=pid,
        name=pid,
        sku=pid,
        category="Test",
        active=True,
        stock=stock,
        reorder=2,
        price=1000,
        cost=500,
        created=(TODAY - timedelta(days=days)).isoformat(),
    )


def sales(pid="p", days=80, amount=4):
    return [
        dict(
            product=pid,
            day=(TODAY - timedelta(days=i)).isoformat(),
            units=amount,
            gross=amount * 1000,
        )
        for i in range(1, days + 1)
    ]


def test_calendar_boundaries():
    assert window("last_week", date(2026, 10, 26)) == (
        date(2026, 10, 19),
        date(2026, 10, 25),
    )
    assert window("last_month", date(2026, 1, 3)) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )
    assert window("last7", TODAY) == (date(2026, 10, 16), date(2026, 10, 22))


def test_constant_demand_stockout_reorder():
    d = analyze([product()], sales(), today=TODAY)
    f = d["forecasts"][0]
    assert f["next7"] == 28 and f["next30"] == 120
    assert f["stockout_in_days"] == 3 and f["stockout_date"] == "2026-10-26"
    assert f["reorder_qty"] == 168 and f["wape"] == 0 and f["quality"] == "Moderate"


def test_new_product_abstains_even_with_sales():
    f = analyze([product(days=3)], sales(days=2), today=TODAY)["forecasts"][0]
    assert f["next30"] is None and f["reorder_qty"] is None
    assert f["quality"] == "Insufficient history"


def test_zero_sales_ranked_least_and_not_forecast():
    d = analyze([product(), product("zero")], sales(), today=TODAY)
    assert d["least"][0]["id"] == "zero" and d["least"][0]["units"] == 0
    f = next(f for f in d["forecasts"] if f["id"] == "zero")
    assert f["next30"] is None
    assert d["summary"]["slow_moving"] == 1


def test_today_does_not_leak_into_training():
    records = sales() + [
        dict(product="p", day=TODAY.isoformat(), units=9999, gross=9999000)
    ]
    d = analyze([product()], records, period="today", today=TODAY)
    assert d["summary"]["units"] == 9999 and d["forecasts"][0]["next7"] == 28


def test_current_out_of_stock_without_prediction():
    f = analyze([product(days=2, stock=0)], [], today=TODAY)["forecasts"][0]
    assert f["risk"] == "Out of stock" and f["stockout_date"] == TODAY.isoformat()
    assert f["next30"] is None


def test_archived_products_rank_but_not_forecast():
    p = product()
    p["active"] = False
    d = analyze([p], sales(), today=TODAY)
    assert len(d["rankings"]) == 1 and d["forecasts"] == []


def test_zero_holdout_has_no_wape_percentage():
    records = [r for r in sales() if r["day"] < (TODAY - timedelta(days=7)).isoformat()]
    f = analyze([product()], records, today=TODAY)["forecasts"][0]
    assert f["wape"] is None


def test_weekday_pattern_and_start_offset():
    dates = [TODAY - timedelta(days=56 - i) for i in range(56)]
    history = [10 if d.weekday() == 0 else 0 for d in dates]
    pred = rates(history, dates, "weekday", offset=2)
    assert pred[0] == (10 if (TODAY + timedelta(days=1)).weekday() == 0 else 0)
    assert sum(pred[:7]) == 10


def test_last_sale_from_all_time_metadata():
    p = product(days=400)
    p["last_sale"] = (TODAY - timedelta(days=140)).isoformat()
    f = analyze([p], [], today=TODAY)["forecasts"][0]
    assert f["days_unsold"] == 140
