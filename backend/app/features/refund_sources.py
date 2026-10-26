"""Refund capacity follows recorded collections and consumed exchange credit."""

import json
from ..rules import fail
from .taxation import allocate_discount


def obj(v):
    return json.loads(v) if isinstance(v, str) else v


async def plan(c, tenant, sale, credit, replacement_total):
    sources = []
    for row in await c.fetch(
        "SELECT * FROM sale_tenders WHERE tenant=$1 AND sale=$2 ORDER BY id",
        tenant,
        sale,
    ):
        origin = obj(row["origin"]) or {}
        # Legacy exchange credit has no payment-method provenance; never invent it.
        if row["method_name"] == "Return credit" and not origin:
            return {
                "available": False,
                "reason": "This invoice contains older exchange credit without payment provenance. Use manual settlement.",
            }
        sources.append(
            {
                "source": "tender:" + row["id"],
                "method_id": row["method_id"],
                "name": row["method_name"],
                "name_ur": row["method_name_ur"],
                "is_cash": row["is_cash"],
                "amount": row["amount"],
                "reference": row["reference"],
                "origin": origin
                or {"sale": sale, "tender": row["id"], "reference": row["reference"]},
            }
        )
    recoveries = await c.fetch(
        "SELECT p.*,a.amount AS applied FROM customer_payments p JOIN payment_allocations a ON a.tenant=p.tenant AND a.payment=p.id JOIN receivables r ON r.tenant=a.tenant AND r.id=a.receivable WHERE r.tenant=$1 AND r.sale=$2 ORDER BY p.created,p.id",
        tenant,
        sale,
    )
    for row in recoveries:
        sources.append(
            {
                "source": "recovery:" + row["id"],
                "method_id": row["method"],
                "name": row["method_name"],
                "name_ur": row["method_name_ur"],
                "is_cash": row["is_cash"],
                "amount": row["applied"],
                "reference": row["reference"],
                "origin": {
                    "sale": sale,
                    "recovery": row["id"],
                    "reference": row["reference"],
                },
            }
        )
    available = {s["source"]: s["amount"] for s in sources}
    previous = await c.fetch(
        "SELECT result FROM sale_adjustments WHERE tenant=$1 AND sale=$2 ORDER BY revision",
        tenant,
        sale,
    )
    for row in previous:
        result = obj(row["result"])
        spent = result.get("available_credit", result["credit"])
        if not spent:
            continue
        usage = result.get("source_usage")
        if usage is None or sum(s["amount"] for s in usage) != spent:
            return {
                "available": False,
                "reason": "An earlier adjustment has no payment allocation evidence. Use manual settlement.",
            }
        for entry in usage:
            key = entry["source"]
            if key not in available or available[key] < entry["amount"]:
                return {
                    "available": False,
                    "reason": "Payment allocation evidence is inconsistent. Use manual settlement.",
                }
            available[key] -= entry["amount"]
    if sum(available.values()) < credit:
        return {
            "available": False,
            "reason": "Recorded payment sources do not cover this credit. Use manual settlement.",
        }
    consumed = allocate_discount([available[s["source"]] for s in sources], credit)
    refund = max(0, credit - replacement_total)
    refunds = allocate_discount(consumed, refund)
    usage = []
    payouts = []
    transfers = []
    for source, amount, pay in zip(sources, consumed, refunds):
        if amount:
            usage.append({**source, "amount": amount})
        if pay:
            payouts.append({**source, "amount": pay})
        if amount - pay:
            transfers.append({**source, "amount": amount - pay})
    return {
        "available": True,
        "usage": usage,
        "refunds": payouts,
        "transfers": transfers,
        "cash_refund": sum(p["amount"] for p in payouts if p["is_cash"]),
    }


def checked_references(plan, references):
    keys = {p["source"] for p in plan["refunds"] if not p["is_cash"]}
    actual = {r.source: r.reference.strip() for r in references}
    if (
        len(actual) != len(references)
        or set(actual) != keys
        or any(not v for v in actual.values())
    ):
        fail(
            "Provide exactly one settlement reference for each non-cash refund source."
        )
    return [
        {**p, "settlement_reference": actual.get(p["source"], "")}
        for p in plan["refunds"]
    ]
