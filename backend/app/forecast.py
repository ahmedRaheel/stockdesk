"""Transparent sales analytics and baseline forecasts. No external AI service.
Only complete UTC days train the forecast; zero-sales days are included.
Forecasts describe observed sales, not unconstrained demand during stockouts.
"""

from datetime import date, datetime, timedelta, timezone
from math import ceil, sqrt
from statistics import mean, pstdev
import plotly.graph_objects as go
import json


def window(period, today):
    if period == "today":
        return today, today
    if period == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if period == "last7":
        return today - timedelta(days=7), today - timedelta(days=1)
    if period == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        return end - timedelta(days=6), end
    if period == "month":
        return today.replace(day=1), today
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if period == "last30":
        return today - timedelta(days=30), today - timedelta(days=1)
    raise ValueError("Unsupported period")


def rates(history, dates, model, offset=1):
    recent = history[-28:]
    base = mean(recent) if recent else 0
    if model == "weekday" and len(history) >= 56:
        past = history[-56:]
        start = dates[-1] - timedelta(days=55)
        return [
            mean(
                [
                    v
                    for i, v in enumerate(past)
                    if (start + timedelta(days=i)).weekday()
                    == (dates[-1] + timedelta(days=h + offset - 1)).weekday()
                ]
            )
            for h in range(1, 31)
        ]
    return [base] * 30


def analyze(products, daily, period="last7", lead=7, cover=30, safety=20, today=None):
    today = today or datetime.now(timezone.utc).date()
    start, end = window(period, today)
    by_product = {}
    all_days = {}
    for r in daily:
        day = date.fromisoformat(str(r["day"])[:10])
        entry = {"units": float(r["units"]), "gross": int(r["gross"])}
        by_product.setdefault(r["product"], {})[day] = entry
        total = all_days.setdefault(day, {"units": 0, "gross": 0})
        total["units"] += entry["units"]
        total["gross"] += entry["gross"]
    rankings = []
    forecasts = []
    future = [0.0] * 30
    for p in products:
        p = {
            **p,
            "stock": float(p["stock"]),
            "reorder": float(p["reorder"]),
            "incoming": float(p.get("incoming", 0)),
        }
        sales = by_product.get(p["id"], {})
        created = date.fromisoformat(str(p["created"])[:10])
        # A product first listed mid-day starts observation on the following full day.
        first = max(today - timedelta(days=90), created + timedelta(days=1))
        n = max(0, (today - first).days)
        dates = [first + timedelta(days=i) for i in range(n)]
        history = [sales.get(d, {}).get("units", 0) for d in dates]
        units = sum(v["units"] for d, v in sales.items() if start <= d <= end)
        gross = sum(v["gross"] for d, v in sales.items() if start <= d <= end)
        last7 = sum(
            v["units"]
            for d, v in sales.items()
            if today - timedelta(days=7) <= d < today
        )
        prev7 = sum(
            v["units"]
            for d, v in sales.items()
            if today - timedelta(days=14) <= d < today - timedelta(days=7)
        )
        row = {
            "id": p["id"],
            "name": p["name"],
            "sku": p["sku"],
            "category": p["category"],
            "active": p["active"],
            "stock": p["stock"],
            "units": units,
            "gross": gross,
            "last7": last7,
            "previous7": prev7,
            "growth_pct": round((last7 - prev7) / prev7 * 100, 1) if prev7 else None,
        }
        rankings.append(row)
        if not p["active"]:
            continue
        selling_days = sum(v > 0 for v in history)
        enough = n >= 14 and selling_days >= 3
        model = "trailing-28-day mean"
        wape = None
        pred = None
        quality = "Insufficient history"
        # Rolling-origin validation: 7 complete holdout days, never current-day sales.
        if n >= 35:
            train = history[:-7]
            train_dates = dates[:-7]
            actual = history[-7:]
            den = sum(actual)
            candidates = [("trailing-28-day mean", "mean")]
            if len(train) >= 56:
                candidates.append(("weekday mean (last 8 weeks)", "weekday"))
            chosen = min(
                candidates,
                key=lambda m: sum(
                    abs(a - f)
                    for a, f in zip(actual, rates(train, train_dates, m[1])[:7])
                ),
            )
            model = chosen[0]
            err = sum(
                abs(a - f)
                for a, f in zip(actual, rates(train, train_dates, chosen[1])[:7])
            )
            wape = round(err / den * 100, 1) if den else None
        if enough:
            pred = rates(
                history,
                dates,
                "weekday" if model.startswith("weekday") else "mean",
                offset=2,
            )
            quality = (
                "Moderate"
                if wape is not None and wape <= 40 and selling_days >= 10
                else "Low"
            )
            for i, v in enumerate(pred):
                future[i] += v
        avg = mean(pred) if pred else None
        sold_dates = [d for d, v in sales.items() if v["units"] > 0 and d <= today]
        last_sale = (
            date.fromisoformat(str(p["last_sale"])[:10])
            if p.get("last_sale")
            else max(sold_dates) if sold_dates else None
        )
        days_unsold = (
            (today - last_sale).days if last_sale else max(0, (today - created).days)
        )
        days_cover = round(p["stock"] / avg, 1) if avg and avg > 0 else None
        stockout = 0 if p["stock"] <= 0 else None
        if pred and p["stock"] > 0:
            running = 0
            for i, v in enumerate(pred):
                running += v
                if running >= p["stock"]:
                    stockout = i + 1
                    break
        reorder = (
            max(
                0,
                ceil(
                    avg * (lead + cover) * (1 + safety / 100)
                    - p["stock"]
                    - p.get("incoming", 0)
                ),
            )
            if avg is not None
            else None
        )
        sigma = pstdev(history[-28:]) if len(history) >= 2 else 0
        f7 = sum(pred[:7]) if pred else None
        f30 = sum(pred) if pred else None
        forecasts.append(
            {
                **row,
                "history_days": n,
                "selling_days": selling_days,
                "quality": quality,
                "model": model if enough else None,
                "wape": wape,
                "daily_rate": round(avg, 2) if avg is not None else None,
                "next7": round(f7, 1) if f7 is not None else None,
                "next30": round(f30, 1) if f30 is not None else None,
                "range30": (
                    [
                        round(max(0, f30 - 1.64 * sigma * sqrt(30)), 1),
                        round(f30 + 1.64 * sigma * sqrt(30), 1),
                    ]
                    if f30 is not None
                    else None
                ),
                "days_cover": days_cover,
                "stockout_in_days": stockout,
                "stockout_date": (
                    (today + timedelta(days=stockout)).isoformat()
                    if stockout is not None
                    else None
                ),
                "reorder_qty": reorder,
                "incoming": p.get("incoming", 0),
                "risk": (
                    "Out of stock"
                    if p["stock"] <= 0
                    else (
                        "At risk"
                        if stockout is not None and stockout <= lead
                        else (
                            "Slow moving"
                            if days_unsold >= 30
                            else "No forecast" if not enough else "Covered"
                        )
                    )
                ),
                "last_sale": last_sale.isoformat() if last_sale else None,
                "days_unsold": days_unsold,
                "overstock_units": (
                    max(0, p["stock"] - ceil(avg * 90)) if avg is not None else None
                ),
                "sales_value30": round(f30 * p["price"]) if f30 is not None else None,
            }
        )
    top = sorted(rankings, key=lambda r: (-r["units"], r["sku"]))
    least = sorted(rankings, key=lambda r: (r["units"], r["sku"]))
    rising = sorted(
        [r for r in rankings if r["last7"] > r["previous7"]],
        key=lambda r: r["last7"] - r["previous7"],
        reverse=True,
    )
    decreasing = sorted(
        [r for r in rankings if r["last7"] < r["previous7"]],
        key=lambda r: r["last7"] - r["previous7"],
    )
    days = [today - timedelta(days=29 - i) for i in range(30)]
    fig = go.Figure()
    fig.add_scatter(
        x=[d.isoformat() for d in days],
        y=[all_days.get(d, {}).get("units", 0) for d in days],
        mode="lines+markers",
        name="Observed units",
        line_color="#426b9d",
    )
    if any(f["next30"] is not None for f in forecasts):
        fig.add_scatter(
            x=[(today + timedelta(days=i)).isoformat() for i in range(1, 31)],
            y=[round(v, 2) for v in future],
            mode="lines",
            name="Forecast · eligible products",
            line=dict(color="#d39c35", dash="dash"),
        )
    fig.update_layout(
        template="plotly_white",
        height=310,
        margin=dict(l=45, r=15, t=10, b=45),
        legend=dict(orientation="h", y=1.15),
        yaxis_title="Units",
        hovermode="x unified",
        font_size=11,
    )
    monthly = {}
    for d, v in all_days.items():
        key = d.strftime("%Y-%m")
        m = monthly.setdefault(key, {"month": key, "units": 0, "gross": 0})
        m["units"] += v["units"]
        m["gross"] += v["gross"]
    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "as_of": today.isoformat(),
        "lead_days": lead,
        "cover_days": cover,
        "safety_pct": safety,
        "rankings": top,
        "top": top[:10],
        "least": least[:10],
        "rising": rising[:10],
        "declining": decreasing[:10],
        "forecasts": sorted(
            forecasts,
            key=lambda f: (
                f["stockout_in_days"] is None,
                f["stockout_in_days"] or 0,
                f["sku"],
            ),
        ),
        "monthly": sorted(monthly.values(), key=lambda m: m["month"]),
        "daily": [
            {"day": d.isoformat(), **all_days.get(d, {"units": 0, "gross": 0})}
            for d in days
        ],
        "chart": json.loads(fig.to_json()),
        "summary": {
            "units": sum(r["units"] for r in rankings),
            "gross": sum(r["gross"] for r in rankings),
            "forecast30": round(sum(future), 1),
            "eligible": sum(f["next30"] is not None for f in forecasts),
            "active": len(forecasts),
            "out_of_stock": sum(f["stock"] <= 0 for f in forecasts),
            "at_risk": sum(f["risk"] == "At risk" for f in forecasts),
            "slow_moving": sum(
                f["days_unsold"] >= 30 and f["stock"] > 0 for f in forecasts
            ),
        },
    }
