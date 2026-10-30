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


def test_open_purchase_quantities_reduce_reorder_not_stockout():
    from decimal import Decimal

    p = {**product(), "incoming": Decimal("100.5")}
    f = analyze([p], sales(), today=TODAY)["forecasts"][0]
    assert f["reorder_qty"] == 68
    assert f["stockout_in_days"] == 3


def test_event_dates_reorder_and_independent_baseline():
    base = analyze([product()], sales(), today=TODAY)["forecasts"][0]
    scenario = analyze(
        [product()], sales(), today=TODAY, event_pct=100, event_start=2, event_days=3
    )["forecasts"][0]
    assert scenario["next30"] == 132 and scenario["next7"] == 40
    assert scenario["baseline_next30"] == 120 and scenario["reorder_qty"] == 182
    assert scenario["evaluation"] == base["evaluation"] and scenario["range30"] is None
    assert [d["planned"] for d in scenario["daily_forecast"][:5]] == [4, 8, 8, 8, 4]
    assert scenario["daily_forecast"][0]["day"] == str(TODAY + timedelta(days=1))
    short = analyze(
        [product()],
        sales(),
        today=TODAY,
        lead=1,
        cover=1,
        event_pct=100,
        event_start=10,
        event_days=2,
    )["forecasts"][0]
    assert (
        short["reorder_qty"] == 0
    )  # Event outside the requested replenishment window.
    all_days = analyze(
        [product()], sales(), today=TODAY, event_pct=100, event_start=1, event_days=30
    )["forecasts"][0]
    assert all_days["reorder_qty"] == 312  # Uplift must not extend beyond day 30.


def test_model_selection_does_not_use_final_test_week():
    from app.forecast import evaluate

    dates = [TODAY - timedelta(days=90 - i) for i in range(90)]
    history = [20 if d.weekday() == 0 else 1 for d in dates]
    result = evaluate(history, dates)
    changed = evaluate(history[:-7] + [1000] * 7, dates)
    assert result["model"] == "weekday"
    assert (
        result["model"] == changed["model"]
        and result["candidates"] == changed["candidates"]
    )
    assert result["selection_days"] == 21 and result["test_days"] == 7
    assert result["wape"] == 0 and changed["mae"] > 900
    assert result["test_start"] == str(dates[-7])


def test_zero_event_and_sparse_evaluation():
    from app.forecast import evaluate

    f = analyze([product()], sales(), today=TODAY, event_pct=-100, event_days=30)[
        "forecasts"
    ][0]
    assert f["next30"] == 0 and f["next7"] == 0 and f["stockout_date"] is None
    assert f["baseline_next30"] == 120
    dates = [TODAY - timedelta(days=35 - i) for i in range(35)]
    e = evaluate([0] * 35, dates)
    assert (
        e["selection_days"] == 0
        and e["wape"] is None
        and e["bias_pct"] is None
        and e["mae"] == 0
    )
