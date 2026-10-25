"""Read-only, bounded descriptive analytics. All money is integer minor units."""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
import json
from zoneinfo import ZoneInfo
from ..rules import fail, line_amount


def tax_register(sales):
    groups = {}
    invoices = []
    for s in sales:
        snapshot = s.get("tax_snapshot") or {}
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        lines = snapshot.get("lines") or []
        if lines:
            if (
                sum(int(x["tax"]) for x in lines) != s["tax"]
                or sum(int(x["tax"]) for x in lines if x["inclusive"])
                != s["tax_included"]
                or sum(int(x["taxable"]) for x in lines)
                != s["subtotal"] - s["discount"] - s["tax_included"]
            ):
                fail(
                    "Invoice tax snapshot is inconsistent; report was not generated.",
                    409,
                )
        elif s["tax_included"]:
            fail("Invoice tax snapshot is inconsistent; report was not generated.", 409)
        else:
            lines = [
                dict(
                    profile_id=None,
                    name="Manual / legacy",
                    rate_bps=s["tax_bps"],
                    inclusive=False,
                    taxable=s["subtotal"] - s["discount"],
                    tax=s["tax"],
                )
            ]
        for row in lines:
            key = (
                row.get("profile_id"),
                row.get("name", ""),
                row["rate_bps"],
                row["inclusive"],
            )
            g = groups.setdefault(
                key,
                dict(
                    profile=key[1] or "No tax profile",
                    rate_bps=key[2],
                    inclusive=key[3],
                    taxable=0,
                    tax=0,
                ),
            )
            g["taxable"] += int(row["taxable"])
            g["tax"] += int(row["tax"])
        invoices.append(
            dict(
                invoice=s["invoice_number"],
                day=s["day"],
                taxable=s["subtotal"] - s["discount"] - s["tax_included"],
                tax=s["tax"],
                tax_included=s["tax_included"],
                tax_added=s["tax"] - s["tax_included"],
                total=s["total"],
            )
        )
    return dict(
        groups=list(groups.values()),
        invoices=invoices,
        summary={
            k: sum(x[k] for x in invoices)
            for k in ("taxable", "tax", "tax_included", "tax_added", "total")
        },
    )


def stock_age(batches, today):
    result = []
    summary = {
        k: 0 for k in ("current_cost_value", "expired_value", "near_expiry_value")
    }
    for b in batches:
        created = b["created"].astimezone(ZoneInfo("Asia/Karachi")).date()
        age = max(0, (today - created).days)
        days_left = (b["expires"] - today).days if b["expires"] else None
        value = line_amount(b["cost"], Decimal(b["stock"]))
        status = (
            "Expired"
            if days_left is not None and days_left < 0
            else (
                "Near expiry"
                if days_left is not None and days_left <= 30
                else "Available"
            )
        )
        summary["current_cost_value"] += value
        if status == "Expired":
            summary["expired_value"] += value
        if status == "Near expiry":
            summary["near_expiry_value"] += value
        result.append(
            dict(
                id=b["id"],
                sku=b["sku"],
                name=b["name"],
                lot=b["lot"],
                units=str(b["stock"]),
                unit=b["unit_name"],
                age_days=age,
                age_band=(
                    "0–30"
                    if age <= 30
                    else "31–60" if age <= 60 else "61–90" if age <= 90 else "91+"
                ),
                expires=b["expires"],
                days_to_expiry=days_left,
                status=status,
                current_cost_value=value,
            )
        )
    return dict(summary=summary, batches=result, as_of=today)


def basket_analysis(sales, items, products, minimum=2):
    baskets = defaultdict(set)
    valid = {s["id"] for s in sales}
    for row in items:
        if row["sale"] in valid:
            baskets[row["sale"]].add(row["product"])
    counts, pairs = Counter(), Counter()
    for basket in baskets.values():
        if len(basket) > 100:
            fail(
                "Basket analysis supports at most 100 distinct products per invoice.",
                422,
            )
        counts.update(basket)
        pairs.update(combinations(sorted(basket), 2))
    names = {p["id"]: p for p in products}
    n = len(sales)
    result = []
    for (a, b), count in pairs.items():
        if count < minimum:
            continue
        result.append(
            dict(
                product_a=names[a]["name"],
                sku_a=names[a]["sku"],
                product_b=names[b]["name"],
                sku_b=names[b]["sku"],
                baskets=count,
                support_pct=round(count / n * 100, 2),
                confidence_a_b_pct=round(count / counts[a] * 100, 2),
                confidence_b_a_pct=round(count / counts[b] * 100, 2),
                lift=round(count * n / (counts[a] * counts[b]), 4),
            )
        )
    result.sort(key=lambda x: (-x["baskets"], -x["lift"], x["sku_a"], x["sku_b"]))
    return dict(
        invoices=n,
        minimum_baskets=minimum,
        qualifying_pairs=len(result),
        pairs=result[:200],
    )


def scenario(summary, observed_days, horizon_days, demand_pct, price_pct, cost_pct):
    """User-controlled sensitivity calculation; not elasticity or a forecast model."""

    def amount(value):
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    scale = Decimal(horizon_days) / Decimal(observed_days)
    demand = 1 + Decimal(str(demand_pct)) / 100
    price = 1 + Decimal(str(price_pct)) / 100
    cost = 1 + Decimal(str(cost_pct)) / 100
    baseline_net = amount(Decimal(summary["net_sales"]) * scale)
    baseline_cost = amount(Decimal(summary["cost"]) * scale)
    net = amount(Decimal(summary["net_sales"]) * scale * demand * price)
    expense = amount(Decimal(summary["cost"]) * scale * demand * cost)
    return dict(
        observed_days=observed_days,
        horizon_days=horizon_days,
        baseline_net_sales=baseline_net,
        baseline_cost=baseline_cost,
        baseline_profit=baseline_net - baseline_cost,
        net_sales=net,
        cost=expense,
        profit=net - expense,
        profit_change=(net - expense) - (baseline_net - baseline_cost),
        margin_pct=round((net - expense) / net * 100, 2) if net else None,
    )
