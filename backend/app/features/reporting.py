"""Auditable sales-margin and ABC/XYZ analysis; descriptive statistics, not predictions."""

from collections import defaultdict
import json
from zoneinfo import ZoneInfo
from datetime import timedelta
from decimal import Decimal
from math import sqrt
from .taxation import allocate_discount
from ..rules import line_amount, fail


def analyze(sales, items, products, days, end):
    by_sale = defaultdict(list)
    for row in items:
        by_sale[row["sale"]].append(row)
    sku = {
        p["id"]: {
            "id": p["id"],
            "sku": p["sku"],
            "name": p["name"],
            "category": p["category"],
            "created": p["created"],
            "net_sales": 0,
            "cost": 0,
            "units": 0.0,
            "daily": defaultdict(float),
        }
        for p in products
    }
    categories = defaultdict(lambda: {"net_sales": 0, "cost": 0, "units": 0.0})
    cashiers = defaultdict(lambda: {"net_sales": 0, "cost": 0, "invoices": 0})
    hours = {h: {"hour": h, "net_sales": 0, "invoices": 0} for h in range(24)}
    total_net = total_cost = total_tax = 0
    for sale in sales:
        rows = by_sale[sale["id"]]
        amounts = [int(r["line_total"]) for r in rows]
        discounts = allocate_discount(amounts, int(sale["discount"]))
        snapshot = sale.get("tax_snapshot") or {}
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        saved_deductions = snapshot.get("lines") or snapshot.get("promotion", {}).get(
            "line_discounts"
        )
        if saved_deductions and all("discount" in x for x in saved_deductions):
            by_product = {x["product"]: int(x["discount"]) for x in saved_deductions}
            if set(by_product) != {r["product"] for r in rows}:
                fail(
                    "Invoice discount snapshot is inconsistent; report was not generated.",
                    409,
                )
            discounts = [by_product[r["product"]] for r in rows]
            if sum(discounts) != int(sale["discount"]) or any(
                d < 0 or d > a for d, a in zip(discounts, amounts)
            ):
                fail(
                    "Invoice discount snapshot is inconsistent; report was not generated.",
                    409,
                )
        included_by_product = {
            x["product"]: int(x["tax"])
            for x in snapshot.get("lines", [])
            if x.get("inclusive")
        }
        included = [included_by_product.get(r["product"], 0) for r in rows]
        if sum(included) != int(sale["tax_included"]):
            fail("Invoice tax snapshot is inconsistent; report was not generated.", 409)
        cashier = cashiers[sale["actor"]]
        cashier["invoices"] += 1
        hours[sale["hour"]]["invoices"] += 1
        total_tax += int(sale["tax"])
        for row, discount, tax_in in zip(rows, discounts, included):
            p = sku[row["product"]]
            net = int(row["line_total"]) - discount - tax_in
            cost = line_amount(row["cost"], Decimal(row["quantity"]))
            qty = float(row["quantity"])
            p["net_sales"] += net
            p["cost"] += cost
            p["units"] += qty
            p["daily"][sale["day"]] += qty
            cat = categories[p["category"]]
            cat["net_sales"] += net
            cat["cost"] += cost
            cat["units"] += qty
            cashier["net_sales"] += net
            cashier["cost"] += cost
            hours[sale["hour"]]["net_sales"] += net
            total_net += net
            total_cost += cost
    cumulative = 0
    ranked = sorted(sku.values(), key=lambda p: (-p["net_sales"], p["sku"]))
    start = end - timedelta(days=days - 1)
    for p in ranked:
        p["abc"] = (
            "A"
            if total_net and cumulative / total_net < 0.8 and p["net_sales"]
            else (
                "B"
                if total_net and cumulative / total_net < 0.95 and p["net_sales"]
                else "C"
            )
        )
        cumulative += p["net_sales"]
        p["profit"] = p["net_sales"] - p["cost"]
        p["margin_pct"] = (
            round(p["profit"] / p["net_sales"] * 100, 2) if p["net_sales"] else None
        )
        created = p.pop("created").astimezone(ZoneInfo("Asia/Karachi")).date()
        observed_start = max(start, created + timedelta(days=1))
        n = max(0, (end - observed_start).days + 1)
        units = [
            p["daily"].get(observed_start + timedelta(days=i), 0) for i in range(n)
        ]
        avg = sum(units) / n if n else 0
        cv = sqrt(sum((v - avg) ** 2 for v in units) / n) / avg if n and avg else None
        p["cv"] = round(cv, 3) if cv is not None else None
        p["observed_days"] = n
        p["xyz"] = (
            "Insufficient history"
            if n < 14
            else (
                "No sales" if not avg else "X" if cv <= 0.5 else "Y" if cv <= 1 else "Z"
            )
        )
        p.pop("daily")
    return {
        "summary": {
            "net_sales": total_net,
            "cost": total_cost,
            "profit": total_net - total_cost,
            "tax": total_tax,
            "invoices": len(sales),
        },
        "products": ranked,
        "categories": [
            {"category": k, **v, "profit": v["net_sales"] - v["cost"]}
            for k, v in sorted(categories.items())
        ],
        "cashiers": [
            {"cashier": k, **v, "profit": v["net_sales"] - v["cost"]}
            for k, v in sorted(cashiers.items())
        ],
        "hours": list(hours.values()),
        "start": start,
        "end": end,
        "timezone": "Asia/Karachi",
    }
