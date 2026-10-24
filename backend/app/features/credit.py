"""Khata subledger. Callers hold the tenant lock and own the transaction.

Positive entries increase debt, negative entries decrease it. Balances are derived,
never independently edited. Recoveries allocate oldest due documents first.
"""

import calendar
from datetime import date, timedelta
from ..rules import fail, business_date
from ..service import uid, audit


def schedule(total, count, first, frequency):
    if count < 1 or count > 60 or total < count:
        fail("Installments must be 1–60 and each must contain at least one minor unit.")
    if frequency not in ("weekly", "fortnightly", "monthly"):
        fail("Invalid installment frequency.")
    quotient, remainder = divmod(total, count)
    result = []
    for i in range(count):
        if frequency == "monthly":
            month_index = first.year * 12 + first.month - 1 + i
            year, month = divmod(month_index, 12)
            month += 1
            due = date(year, month, min(first.day, calendar.monthrange(year, month)[1]))
        else:
            due = first + timedelta(days=i * (7 if frequency == "weekly" else 14))
        result.append(
            {
                "sequence": i + 1,
                "due_date": due,
                "amount": quotient + (1 if i < remainder else 0),
            }
        )
    return result


async def customer_balance(c, tenant, customer):
    return await c.fetchval(
        "SELECT COALESCE(SUM(amount),0)::bigint FROM customer_ledger WHERE tenant=$1 AND customer=$2",
        tenant,
        customer,
    )


async def document_balance(c, tenant, receivable):
    return await c.fetchval(
        "SELECT COALESCE(SUM(amount),0)::bigint FROM customer_ledger WHERE tenant=$1 AND receivable=$2",
        tenant,
        receivable,
    )


async def ledger(c, tenant, customer, receivable, kind, amount, reference, actor):
    if amount:
        await c.execute(
            "INSERT INTO customer_ledger(id,tenant,customer,receivable,kind,amount,reference,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",
            uid(),
            tenant,
            customer,
            receivable,
            kind,
            amount,
            reference,
            actor,
        )


async def overdue(c, tenant, customer):
    # With a plan, the unpaid schedule controls overdue status, not the old invoice due date.
    return await c.fetchval(
        """SELECT EXISTS(
      SELECT 1 FROM receivables r WHERE r.tenant=$1 AND r.customer=$2 AND r.status='open' AND
      ((NOT EXISTS(SELECT 1 FROM installment_plans p WHERE p.tenant=r.tenant AND p.receivable=r.id) AND r.due_date<(now() AT TIME ZONE 'Asia/Karachi')::date)
      OR EXISTS(SELECT 1 FROM installment_plans p JOIN installment_schedule s ON s.tenant=p.tenant AND s.plan=p.id WHERE p.tenant=r.tenant AND p.receivable=r.id AND s.due_date<(now() AT TIME ZONE 'Asia/Karachi')::date AND s.paid<s.amount)))""",
        tenant,
        customer,
    )


async def check_credit(c, tenant, customer_id, amount):
    customer = await c.fetchrow(
        "SELECT * FROM customers WHERE tenant=$1 AND id=$2 AND active=true FOR UPDATE",
        tenant,
        customer_id,
    )
    if not customer:
        fail("Active customer not found.", 404)
    if not customer["credit_enabled"]:
        fail("Customer credit requires manager approval.", 409)
    if (
        await customer_balance(c, tenant, customer_id) + amount
        > customer["credit_limit"]
    ):
        fail("Credit limit exceeded. Request a limit increase before checkout.", 409)
    if await overdue(c, tenant, customer_id):
        fail("Overdue payments block new credit. Record recovery first.", 409)
    return customer


async def create_receivable(c, tenant, customer, sale, amount, due, actor, invoice):
    rid = uid()
    await c.execute(
        "INSERT INTO receivables(id,tenant,customer,sale,principal,due_date) VALUES($1,$2,$3,$4,$5,$6)",
        rid,
        tenant,
        customer,
        sale,
        amount,
        due,
    )
    await ledger(c, tenant, customer, rid, "sale", amount, invoice, actor)
    return rid


async def recover(c, u, tenant, b):
    import json

    signature = json.dumps(b, sort_keys=True)
    prior = await c.fetchrow(
        "SELECT id,signature FROM customer_payments WHERE tenant=$1 AND request=$2",
        tenant,
        b["request"],
    )
    if prior:
        if prior["signature"] != signature:
            fail("Request ID already used with different recovery data.", 409)
        return {"id": prior["id"], "replayed": True}
    from .reference import lookup

    method = await lookup(c, tenant, b["method"], "payment_method")
    customer = await c.fetchrow(
        "SELECT * FROM customers WHERE tenant=$1 AND id=$2 FOR UPDATE",
        tenant,
        b["customer"],
    )
    if not customer:
        fail("Customer not found.", 404)
    balance = await customer_balance(c, tenant, b["customer"])
    if b["amount"] > balance:
        fail("Recovery exceeds the outstanding balance.", 409)
    pid = uid()
    remaining = b["amount"]
    await c.execute(
        "INSERT INTO customer_payments(id,tenant,customer,request,signature,amount,method,reference,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        pid,
        tenant,
        b["customer"],
        b["request"],
        signature,
        b["amount"],
        b["method"],
        b["reference"],
        u["email"],
    )
    documents = await c.fetch(
        "SELECT * FROM receivables WHERE tenant=$1 AND customer=$2 AND status='open' ORDER BY due_date,created,id FOR UPDATE",
        tenant,
        b["customer"],
    )
    for document in documents:
        if remaining <= 0:
            break
        outstanding = await document_balance(c, tenant, document["id"])
        allocation = min(remaining, outstanding)
        if not allocation:
            continue
        await ledger(
            c,
            tenant,
            b["customer"],
            document["id"],
            "recovery",
            -allocation,
            pid,
            u["email"],
        )
        await c.execute(
            "INSERT INTO payment_allocations(tenant,payment,receivable,amount) VALUES($1,$2,$3,$4)",
            tenant,
            pid,
            document["id"],
            allocation,
        )
        remainder = allocation
        installments = await c.fetch(
            "SELECT s.* FROM installment_schedule s JOIN installment_plans p ON p.tenant=s.tenant AND p.id=s.plan WHERE p.tenant=$1 AND p.receivable=$2 AND s.paid<s.amount ORDER BY s.sequence FOR UPDATE OF s",
            tenant,
            document["id"],
        )
        for installment in installments:
            applied = min(remainder, installment["amount"] - installment["paid"])
            await c.execute(
                "UPDATE installment_schedule SET paid=paid+$1 WHERE id=$2",
                applied,
                installment["id"],
            )
            remainder -= applied
        if allocation == outstanding:
            await c.execute(
                "UPDATE receivables SET status='settled' WHERE tenant=$1 AND id=$2",
                tenant,
                document["id"],
            )
        remaining -= allocation
    if remaining:
        fail("Ledger reconciliation failed. No recovery was posted.", 409)
    if method["code"] == "cash":
        till = await c.fetchval(
            "SELECT id FROM till_sessions WHERE tenant=$1 AND actor=$2 AND status='open'",
            tenant,
            u["id"],
        )
        if till:
            await c.execute(
                "INSERT INTO till_cash_movements(id,tenant,session,request,amount,reason,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
                uid(),
                tenant,
                till,
                "recovery:" + pid,
                b["amount"],
                "Customer recovery " + pid,
                u["email"],
            )
    await audit(
        c,
        tenant,
        u,
        "Customer recovery",
        {"payment": pid, "customer": b["customer"], "amount": b["amount"]},
    )
    return {"id": pid, "balance": balance - b["amount"]}


async def make_plan(c, u, tenant, b):
    document = await c.fetchrow(
        "SELECT * FROM receivables WHERE tenant=$1 AND id=$2 AND status='open' FOR UPDATE",
        tenant,
        b["receivable"],
    )
    if not document:
        fail("Open receivable not found.", 404)
    if await c.fetchval(
        "SELECT 1 FROM installment_plans WHERE tenant=$1 AND receivable=$2",
        tenant,
        document["id"],
    ):
        fail("A plan already exists for this invoice.", 409)
    balance = await document_balance(c, tenant, document["id"])
    first = date.fromisoformat(b["first_due"])
    if first < business_date():
        fail("First due date cannot be in the past.")
    items = schedule(balance + b["markup"], b["installments"], first, b["frequency"])
    customer = await c.fetchrow(
        "SELECT * FROM customers WHERE tenant=$1 AND id=$2",
        tenant,
        document["customer"],
    )
    if (
        await customer_balance(c, tenant, document["customer"]) + b["markup"]
        > customer["credit_limit"]
    ):
        fail("Markup would exceed the approved credit limit.", 409)
    plan = uid()
    await c.execute(
        "INSERT INTO installment_plans(id,tenant,receivable,frequency,installments,markup,agreed_total,first_due,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        plan,
        tenant,
        document["id"],
        b["frequency"],
        b["installments"],
        b["markup"],
        balance + b["markup"],
        first,
        u["email"],
    )
    for item in items:
        await c.execute(
            "INSERT INTO installment_schedule(id,tenant,plan,sequence,due_date,amount) VALUES($1,$2,$3,$4,$5,$6)",
            uid(),
            tenant,
            plan,
            item["sequence"],
            item["due_date"],
            item["amount"],
        )
    await ledger(
        c,
        tenant,
        document["customer"],
        document["id"],
        "markup",
        b["markup"],
        plan,
        u["email"],
    )
    await audit(
        c,
        tenant,
        u,
        "Installment plan agreed",
        {"plan": plan, "receivable": document["id"], "markup": b["markup"]},
    )
    return {"id": plan, "schedule": items}


async def reverse_credit_sale(c, u, tenant, sale):
    document = await c.fetchrow(
        "SELECT * FROM receivables WHERE tenant=$1 AND sale=$2 FOR UPDATE",
        tenant,
        sale["id"],
    )
    if not document:
        return 0
    balance = await document_balance(c, tenant, document["id"])
    paid = await c.fetchval(
        "SELECT COALESCE(SUM(amount),0)::bigint FROM payment_allocations WHERE tenant=$1 AND receivable=$2",
        tenant,
        document["id"],
    )
    await ledger(
        c,
        tenant,
        document["customer"],
        document["id"],
        "return",
        -balance,
        "Return " + sale["invoice_number"],
        u["email"],
    )
    await c.execute(
        "UPDATE receivables SET status='cancelled' WHERE tenant=$1 AND id=$2",
        tenant,
        document["id"],
    )
    # Paid cash is not automatically moved. The audited amount is due for external refund.
    return sale["paid_now"] + paid
