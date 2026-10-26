"""Operational X/Z evidence. No claim of a tax-authority certified fiscal device."""

import json
from collections import defaultdict
from .. import service, security


def obj(value):
    return json.loads(value) if isinstance(value, str) else value


async def record_return(c, tenant, sale, actor, source, total, tax):
    till = await c.fetchval(
        "SELECT id FROM till_sessions WHERE tenant=$1 AND actor=$2 AND status='open'",
        tenant,
        actor["id"],
    )
    await c.execute(
        "INSERT INTO till_return_events(id,tenant,sale,till_session,source,total,tax,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",
        service.uid(),
        tenant,
        sale,
        till,
        source,
        total,
        tax,
        actor["email"],
    )


async def build(c, tenant, session, kind="X", number=None):
    business = await c.fetchrow(
        "SELECT name,currency,tax_number FROM tenants WHERE id=$1", tenant
    )
    sales = await c.fetch(
        "SELECT * FROM sales WHERE tenant=$1 AND till_session=$2 ORDER BY created,id",
        tenant,
        session["id"],
    )
    all_tenders = await c.fetch(
        "SELECT st.sale,st.method_name,st.is_cash,st.amount FROM sale_tenders st JOIN sales s ON s.tenant=st.tenant AND s.id=st.sale WHERE s.tenant=$1 AND s.till_session=$2 ORDER BY st.id",
        tenant,
        session["id"],
    )
    by_sale = defaultdict(list)
    for part in all_tenders:
        by_sale[part["sale"]].append(part)
    invoices = []
    tender_totals = defaultdict(int)
    subtotal = discount = tax = total = credit = cash = 0
    for current in sales:
        original = obj(current["original_snapshot"]) or {}
        sale = original.get("sale") or dict(current)
        parts = original.get("tenders")
        if parts is None:
            parts = by_sale[current["id"]]
        for part in parts:
            tender_totals[(part["method_name"], bool(part["is_cash"]))] += part[
                "amount"
            ]
        subtotal += sale["subtotal"]
        discount += sale["discount"]
        tax += sale["tax"]
        total += sale["total"]
        credit += sale.get("credit_amount", 0)
        cash += sale.get("cash_amount", 0)
        invoices.append(
            {
                "id": sale["id"],
                "invoice": sale["invoice_number"],
                "total": sale["total"],
                "tax": sale["tax"],
                "discount": sale["discount"],
            }
        )
    returns = service.rows(
        await c.fetch(
            "SELECT sale,source,total,tax,actor,created FROM till_return_events WHERE tenant=$1 AND till_session=$2 ORDER BY created,id",
            tenant,
            session["id"],
        )
    )
    movements = service.rows(
        await c.fetch(
            "SELECT id,amount,reason,actor,created FROM till_cash_movements WHERE tenant=$1 AND session=$2 ORDER BY created,id",
            tenant,
            session["id"],
        )
    )
    returned = sum(r["total"] for r in returns)
    return_tax = sum(r["tax"] for r in returns)
    movement_total = sum(m["amount"] for m in movements)
    return {
        "kind": kind,
        "number": number,
        "business": dict(business),
        "session": dict(session),
        "generated_at": (await c.fetchval("SELECT now()")).isoformat(),
        "totals": {
            "invoice_count": len(invoices),
            "gross_subtotal": subtotal,
            "discounts": discount,
            "sales_tax": tax,
            "gross_sales": total,
            "credit_sales": credit,
            "returns": returned,
            "return_tax": return_tax,
            "net_sales": total - returned,
            "net_tax": tax - return_tax,
            "cash_sales": cash,
            "cash_in": sum(m["amount"] for m in movements if m["amount"] > 0),
            "cash_out": -sum(m["amount"] for m in movements if m["amount"] < 0),
            "opening_cash": session["opening_cash"],
            "expected_cash": session["opening_cash"] + cash + movement_total,
        },
        "tenders": [
            {"method": key[0], "is_cash": key[1], "amount": value}
            for key, value in sorted(tender_totals.items())
        ],
        "invoices": invoices,
        "returns": returns,
        "cash_movements": movements,
        "scope": "Operational till report. Return events start at migration 031. Legacy returns require an actual cash movement; invoice credit does not prove payment. Sales and returns without an open till are excluded.",
    }


async def freeze(c, tenant, session):
    number = await c.fetchval(
        "UPDATE tenants SET z_report_seq=z_report_seq+1 WHERE id=$1 RETURNING z_report_seq",
        tenant,
    )
    report = await build(c, tenant, session, "Z", number)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    digest = security.digest(encoded)
    await c.execute(
        "INSERT INTO till_z_reports(tenant,session,number,snapshot,digest) VALUES($1,$2,$3,$4,$5)",
        tenant,
        session["id"],
        number,
        encoded,
        digest,
    )
    return {"report": json.loads(encoded), "digest": digest}
