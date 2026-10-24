"""Customer credit, installments and configurable lookup HTTP slice."""

from datetime import date
from typing import Literal
from fastapi import APIRouter, Query, Request, Depends
from pydantic import Field
from .contracts import Contract, Identifier, Money
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail, business_date
from ..features import credit

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}",
    dependencies=[Depends(authenticated)],
    tags=["Retail credit and reference data"],
)
Kind = Literal[
    "category",
    "unit",
    "payment_method",
    "adjustment_reason",
    "return_reason",
    "customer_segment",
]


class LookupWrite(Contract):
    kind: Kind
    code: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=150)
    name_ur: str = Field(default="", max_length=150)
    active: bool = Field(default=True, strict=True)
    sort_order: int = Field(default=0, ge=0, le=10000, strict=True)


class CustomerWrite(Contract):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(default="", max_length=30)
    search_aliases: str = Field(default="", max_length=500)
    address: str = Field(default="", max_length=500)
    reference_contact: str = Field(default="", max_length=250)


class CreditRequest(Contract):
    customer: Identifier
    proposed_limit: Money
    reason: str = Field(min_length=1, max_length=500)


class Decision(Contract):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=500)


class Recovery(Contract):
    request: Identifier
    customer: Identifier
    amount: int = Field(strict=True, gt=0, le=100_000_000_000)
    method: Identifier
    reference: str = Field(default="", max_length=150)


class Plan(Contract):
    receivable: Identifier
    frequency: Literal["weekly", "fortnightly", "monthly"]
    installments: int = Field(strict=True, ge=1, le=60)
    first_due: date
    markup: Money = 0


class Promise(Contract):
    promised_date: date
    amount: int = Field(strict=True, gt=0, le=100_000_000_000)
    notes: str = Field(default="", max_length=500)


@router.get("/lookups")
async def lookups(
    tenant: str,
    user: User,
    kind: Kind,
    include_inactive: bool = False,
    q: str = Query("", max_length=100),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant)
        items = await c.fetch(
            "SELECT * FROM lookups WHERE tenant=$1 AND kind=$2 AND ($3 OR active=true) AND ($4='' OR strpos(lower(name||' '||name_ur||' '||code),lower($4))>0) ORDER BY sort_order,name,id LIMIT $5 OFFSET $6",
            tenant,
            kind,
            include_inactive,
            q,
            limit,
            offset,
        )
    return {"items": service.rows(items), "limit": limit, "offset": offset}


@router.post("/lookups", status_code=201)
async def create_lookup(
    tenant: str, payload: LookupWrite, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "settings", lock=True)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO lookups(id,tenant,kind,code,name,name_ur,active,sort_order) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",
                identifier,
                tenant,
                payload.kind,
                payload.code,
                payload.name,
                payload.name_ur,
                payload.active,
                payload.sort_order,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Lookup created",
                {"id": identifier, "kind": payload.kind},
            )
    return {"id": identifier}


@router.put("/lookups/{identifier}")
async def update_lookup(
    tenant: str, identifier: str, payload: LookupWrite, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "settings", lock=True)
            current = await c.fetchrow(
                "SELECT * FROM lookups WHERE tenant=$1 AND id=$2", tenant, identifier
            )
            if not current:
                fail("Lookup not found.", 404)
            if current["kind"] != payload.kind or current["code"] != payload.code:
                fail("Lookup kind and code are immutable.")
            await c.execute(
                "UPDATE lookups SET name=$1,name_ur=$2,active=$3,sort_order=$4 WHERE tenant=$5 AND id=$6",
                payload.name,
                payload.name_ur,
                payload.active,
                payload.sort_order,
                tenant,
                identifier,
            )
            if payload.kind == "category":
                await c.execute(
                    "UPDATE products SET category=$1 WHERE tenant=$2 AND category_id=$3",
                    payload.name,
                    tenant,
                    identifier,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Lookup updated",
                {"id": identifier, "active": payload.active},
            )
    return {"ok": True}


@router.get("/customers")
async def customers(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit")
        items = await c.fetch(
            "SELECT c.*,COALESCE((SELECT SUM(l.amount) FROM customer_ledger l WHERE l.tenant=c.tenant AND l.customer=c.id),0)::bigint AS balance FROM customers c WHERE c.tenant=$1 AND ($2='' OR strpos(lower(c.name||' '||c.phone||' '||c.search_aliases),lower($2))>0) ORDER BY c.name,c.id LIMIT $3 OFFSET $4",
            tenant,
            q,
            limit,
            offset,
        )
    return {"items": service.rows(items), "limit": limit, "offset": offset}


@router.post("/customers", status_code=201)
async def create_customer(
    tenant: str, payload: CustomerWrite, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit", lock=True)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO customers(id,tenant,name,phone,search_aliases,address,reference_contact) VALUES($1,$2,$3,$4,$5,$6,$7)",
                identifier,
                tenant,
                payload.name,
                payload.phone,
                payload.search_aliases,
                payload.address,
                payload.reference_contact,
            )
            await service.audit(c, tenant, user, "Customer created", {"id": identifier})
    return {"id": identifier}


async def statement_data(c, user, tenant, customer):
    await service.authorize(c, user, tenant, "credit")
    person = await c.fetchrow(
        "SELECT * FROM customers WHERE tenant=$1 AND id=$2", tenant, customer
    )
    if not person:
        fail("Customer not found.", 404)
    entries = service.rows(
        await c.fetch(
            "SELECT *,SUM(amount) OVER(ORDER BY created,id)::bigint AS balance FROM customer_ledger WHERE tenant=$1 AND customer=$2 ORDER BY created,id",
            tenant,
            customer,
        )
    )
    documents = service.rows(
        await c.fetch(
            "SELECT r.*,s.invoice_number,COALESCE((SELECT SUM(l.amount) FROM customer_ledger l WHERE l.tenant=r.tenant AND l.receivable=r.id),0)::bigint AS balance FROM receivables r JOIN sales s ON s.tenant=r.tenant AND s.id=r.sale WHERE r.tenant=$1 AND r.customer=$2 ORDER BY r.due_date,r.id",
            tenant,
            customer,
        )
    )
    schedules = service.rows(
        await c.fetch(
            "SELECT s.*,p.receivable,r.status AS document_status FROM installment_schedule s JOIN installment_plans p ON p.tenant=s.tenant AND p.id=s.plan JOIN receivables r ON r.tenant=p.tenant AND r.id=p.receivable WHERE r.tenant=$1 AND r.customer=$2 ORDER BY s.due_date,s.id",
            tenant,
            customer,
        )
    )
    promises = service.rows(
        await c.fetch(
            "SELECT * FROM payment_promises WHERE tenant=$1 AND customer=$2 ORDER BY created DESC LIMIT 100",
            tenant,
            customer,
        )
    )
    payments = service.rows(
        await c.fetch(
            "SELECT p.*,l.name AS method_name FROM customer_payments p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.method WHERE p.tenant=$1 AND p.customer=$2 ORDER BY p.created DESC LIMIT 100",
            tenant,
            customer,
        )
    )
    return {
        "customer": dict(person),
        "entries": entries,
        "documents": documents,
        "schedule": schedules,
        "promises": promises,
        "payments": payments,
        "balance": await credit.customer_balance(c, tenant, customer),
    }


@router.get("/customers/{customer}/statement")
async def statement(tenant: str, customer: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            return await statement_data(c, user, tenant, customer)


@router.post("/credit-requests", status_code=201)
async def request_credit(
    tenant: str, payload: CreditRequest, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit", lock=True)
            if not await c.fetchval(
                "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active=true",
                tenant,
                payload.customer,
            ):
                fail("Customer not found.", 404)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO credit_requests(id,tenant,customer,proposed_limit,reason,requested_by) VALUES($1,$2,$3,$4,$5,$6)",
                identifier,
                tenant,
                payload.customer,
                payload.proposed_limit,
                payload.reason,
                user["id"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Credit approval requested",
                {"id": identifier, "limit": payload.proposed_limit},
            )
    return {"id": identifier}


@router.get("/credit-requests")
async def credit_requests(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit")
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT r.*,c.name AS customer_name,u.name AS requester FROM credit_requests r JOIN customers c ON c.tenant=r.tenant AND c.id=r.customer JOIN users u ON u.id=r.requested_by WHERE r.tenant=$1 ORDER BY r.created DESC LIMIT 200",
                    tenant,
                )
            )
        }


@router.post("/credit-requests/{identifier}/decision")
async def decide_credit(
    tenant: str, identifier: str, payload: Decision, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit_approve", lock=True)
            record = await c.fetchrow(
                "SELECT * FROM credit_requests WHERE tenant=$1 AND id=$2 FOR UPDATE",
                tenant,
                identifier,
            )
            if not record:
                fail("Approval request not found.", 404)
            if record["status"] != "pending":
                fail("This request has already been decided.", 409)
            if record["requested_by"] == user["id"]:
                fail("A different authorized manager must approve this request.", 403)
            if payload.decision == "approved":
                balance = await credit.customer_balance(c, tenant, record["customer"])
                if record["proposed_limit"] < balance:
                    fail("Limit cannot be below the current outstanding balance.", 409)
                await c.execute(
                    "UPDATE customers SET credit_limit=$1,credit_enabled=$2 WHERE tenant=$3 AND id=$4",
                    record["proposed_limit"],
                    record["proposed_limit"] > 0,
                    tenant,
                    record["customer"],
                )
            await c.execute(
                "UPDATE credit_requests SET status=$1,decided_by=$2,decision_note=$3,decided=now() WHERE id=$4",
                payload.decision,
                user["id"],
                payload.note,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Credit request decided",
                {"id": identifier, "decision": payload.decision, "note": payload.note},
            )
    return {"ok": True}


@router.post("/recoveries")
async def recovery(tenant: str, payload: Recovery, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit", lock=True)
            return await credit.recover(c, user, tenant, payload.model_dump())


@router.post("/installment-plans")
async def create_plan(tenant: str, payload: Plan, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit_approve", lock=True)
            return await credit.make_plan(
                c, user, tenant, payload.model_dump(mode="json")
            )


@router.post("/customers/{customer}/promises")
async def promise(
    tenant: str, customer: str, payload: Promise, request: Request, user: User
):
    security.csrf(request)
    if payload.promised_date < business_date():
        fail("Promise date cannot be in the past.")
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit", lock=True)
            if not await c.fetchval(
                "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2", tenant, customer
            ):
                fail("Customer not found.", 404)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO payment_promises(id,tenant,customer,promised_date,amount,notes,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
                identifier,
                tenant,
                customer,
                payload.promised_date,
                payload.amount,
                payload.notes,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Payment promise recorded",
                {"id": identifier, "customer": customer},
            )
    return {"id": identifier}


@router.get("/credit-overview")
async def overview(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit")
        # Plan installments replace invoice dues so the report never counts debt twice.
        dues = service.rows(
            await c.fetch(
                """WITH balances AS(
          SELECT r.*,c.name,c.phone,COALESCE((SELECT SUM(amount) FROM customer_ledger l WHERE l.tenant=r.tenant AND l.receivable=r.id),0)::bigint AS balance
          FROM receivables r JOIN customers c ON c.tenant=r.tenant AND c.id=r.customer WHERE r.tenant=$1 AND r.status='open')
          SELECT b.customer,b.name,b.phone,b.id AS receivable,b.due_date,b.balance AS amount FROM balances b
          WHERE b.balance>0 AND NOT EXISTS(SELECT 1 FROM installment_plans p WHERE p.tenant=b.tenant AND p.receivable=b.id)
          UNION ALL SELECT b.customer,b.name,b.phone,b.id,s.due_date,s.amount-s.paid FROM balances b JOIN installment_plans p ON p.tenant=b.tenant AND p.receivable=b.id JOIN installment_schedule s ON s.tenant=p.tenant AND s.plan=p.id WHERE s.amount>s.paid ORDER BY due_date""",
                tenant,
            )
        )
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    today = datetime.now(ZoneInfo("Asia/Karachi")).date()
    buckets = {"not_due": 0, "days_0_7": 0, "days_8_30": 0, "days_31_plus": 0}
    for item in dues:
        days = (today - item["due_date"]).days
        bucket = (
            "not_due"
            if days < 0
            else (
                "days_0_7"
                if days <= 7
                else "days_8_30" if days <= 30 else "days_31_plus"
            )
        )
        item["days_overdue"] = max(0, days)
        item["bucket"] = bucket
        buckets[bucket] += item["amount"]
    return {
        "as_of": today,
        "buckets": buckets,
        "dues": dues,
        "scheduled_next30": sum(
            x["amount"]
            for x in dues
            if today <= x["due_date"] <= today + timedelta(days=30)
        ),
        "note": "Scheduled contractual amounts, not a probability-based recovery forecast.",
    }


@router.get("/lookups/{identifier}")
async def get_lookup(tenant: str, identifier: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant)
        record = await c.fetchrow(
            "SELECT * FROM lookups WHERE tenant=$1 AND id=$2", tenant, identifier
        )
        if not record:
            fail("Lookup not found.", 404)
    return dict(record)


@router.get("/customers/{customer}/statement.pdf")
async def statement_pdf(tenant: str, customer: str, user: User):
    from fastapi.responses import Response
    from ..pdf import customer_statement_pdf
    import asyncio

    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            data = await statement_data(c, user, tenant, customer)
            business = dict(
                await c.fetchrow("SELECT * FROM tenants WHERE id=$1", tenant)
            )
    content = await asyncio.to_thread(customer_statement_pdf, data, business)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="customer-statement.pdf"'
        },
    )


@router.get("/batches")
async def batches(
    tenant: str,
    user: User,
    product: str = "",
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "stock")
        items = await c.fetch(
            "SELECT b.*,p.name,p.sku FROM stock_batches b JOIN products p ON p.tenant=b.tenant AND p.id=b.product WHERE b.tenant=$1 AND ($2='' OR b.product=$2) AND b.stock>0 ORDER BY b.expires NULLS LAST,b.created,b.id LIMIT $3 OFFSET $4",
            tenant,
            product,
            limit,
            offset,
        )
    return {"items": service.rows(items)}


@router.get("/inventory-alerts")
async def inventory_alerts(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "stock")
        expired = await c.fetch(
            "SELECT b.*,p.name,p.sku FROM stock_batches b JOIN products p ON p.tenant=b.tenant AND p.id=b.product WHERE b.tenant=$1 AND b.stock>0 AND b.expires<(now() AT TIME ZONE 'Asia/Karachi')::date ORDER BY b.expires LIMIT 200",
            tenant,
        )
        near = await c.fetch(
            "SELECT b.*,p.name,p.sku FROM stock_batches b JOIN products p ON p.tenant=b.tenant AND p.id=b.product WHERE b.tenant=$1 AND b.stock>0 AND b.expires BETWEEN (now() AT TIME ZONE 'Asia/Karachi')::date AND (now() AT TIME ZONE 'Asia/Karachi')::date+30 ORDER BY b.expires LIMIT 200",
            tenant,
        )
    return {
        "expired": service.rows(expired),
        "near_expiry": service.rows(near),
        "window_days": 30,
    }


from .contracts import SaleLine


class HoldBill(Contract):
    id: Identifier
    label: str = Field(min_length=1, max_length=100)
    items: list[SaleLine] = Field(min_length=1, max_length=100)
    customer_id: str | None = None


@router.get("/held-bills")
async def held_bills(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "sale")
        items = service.rows(
            await c.fetch(
                "SELECT id,label,payload,created FROM held_bills WHERE tenant=$1 AND actor=$2 AND consumed_sale IS NULL ORDER BY created DESC LIMIT 100",
                tenant,
                user["id"],
            )
        )
    import json

    for item in items:
        item["payload"] = json.loads(item["payload"])
    return {"items": items}


@router.post("/held-bills")
async def hold_bill(tenant: str, payload: HoldBill, request: Request, user: User):
    import json

    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            for line in payload.items:
                if not await c.fetchval(
                    "SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND active=true",
                    tenant,
                    line.id,
                ):
                    fail("Product not found.", 404)
            if payload.customer_id and not await c.fetchval(
                "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2",
                tenant,
                payload.customer_id,
            ):
                fail("Customer not found.", 404)
            value = payload.model_dump(mode="json")
            prior = await c.fetchrow(
                "SELECT * FROM held_bills WHERE tenant=$1 AND id=$2", tenant, payload.id
            )
            if prior:
                if (
                    prior["actor"] != user["id"]
                    or json.loads(prior["payload"]) != value
                ):
                    fail("Held bill identifier already used.", 409)
                return {"id": payload.id}
            await c.execute(
                "INSERT INTO held_bills(id,tenant,actor,label,payload) VALUES($1,$2,$3,$4,$5)",
                payload.id,
                tenant,
                user["id"],
                payload.label,
                json.dumps(value),
            )
            await service.audit(c, tenant, user, "Bill held", {"id": payload.id})
    return {"id": payload.id}


@router.delete("/held-bills/{identifier}")
async def delete_held(tenant: str, identifier: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            await c.execute(
                "DELETE FROM held_bills WHERE tenant=$1 AND id=$2 AND actor=$3 AND consumed_sale IS NULL",
                tenant,
                identifier,
                user["id"],
            )
            await service.audit(
                c, tenant, user, "Held bill discarded", {"id": identifier}
            )
    return {"ok": True}


class OpenTill(Contract):
    opening_cash: Money


class CashMovement(Contract):
    request: Identifier
    type: Literal["IN", "OUT"]
    amount: int = Field(strict=True, gt=0, le=100_000_000_000)
    reason: str = Field(min_length=1, max_length=500)


class CloseTill(Contract):
    counted_cash: Money
    note: str = Field(default="", max_length=500)


async def till_totals(c, tenant, session):
    sales = await c.fetchval(
        "SELECT COALESCE(SUM(paid_now),0)::bigint FROM sales WHERE tenant=$1 AND till_session=$2 AND payment='cash'",
        tenant,
        session["id"],
    )
    movements = await c.fetchval(
        "SELECT COALESCE(SUM(amount),0)::bigint FROM till_cash_movements WHERE tenant=$1 AND session=$2",
        tenant,
        session["id"],
    )
    return {
        "opening": session["opening_cash"],
        "cash_sales": sales,
        "cash_movements": movements,
        "expected": session["opening_cash"] + sales + movements,
    }


@router.get("/tills")
async def tills(tenant: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "sale")
            sessions = service.rows(
                await c.fetch(
                    "SELECT * FROM till_sessions WHERE tenant=$1 AND actor=$2 ORDER BY opened DESC LIMIT 100",
                    tenant,
                    user["id"],
                )
            )
            current = next((s for s in sessions if s["status"] == "open"), None)
            totals = await till_totals(c, tenant, current) if current else None
            movements = (
                service.rows(
                    await c.fetch(
                        "SELECT * FROM till_cash_movements WHERE tenant=$1 AND session=$2 ORDER BY created DESC",
                        tenant,
                        current["id"],
                    )
                )
                if current
                else []
            )
    return {
        "sessions": sessions,
        "current": current,
        "totals": totals,
        "movements": movements,
    }


@router.post("/tills")
async def open_till(tenant: str, payload: OpenTill, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            if await c.fetchval(
                "SELECT 1 FROM till_sessions WHERE tenant=$1 AND actor=$2 AND status='open'",
                tenant,
                user["id"],
            ):
                fail("You already have an open till session.", 409)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO till_sessions(id,tenant,actor,opening_cash) VALUES($1,$2,$3,$4)",
                identifier,
                tenant,
                user["id"],
                payload.opening_cash,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Till opened",
                {"id": identifier, "opening_cash": payload.opening_cash},
            )
    return {"id": identifier}


@router.post("/tills/{identifier}/cash-movements")
async def move_cash(
    tenant: str, identifier: str, payload: CashMovement, request: Request, user: User
):
    security.csrf(request)
    amount = payload.amount if payload.type == "IN" else -payload.amount
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            record = await c.fetchrow(
                "SELECT * FROM till_sessions WHERE tenant=$1 AND id=$2 AND actor=$3 FOR UPDATE",
                tenant,
                identifier,
                user["id"],
            )
            if not record:
                fail("Till session not found.", 404)
            prior = await c.fetchrow(
                "SELECT * FROM till_cash_movements WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if prior:
                if (
                    prior["session"] != identifier
                    or prior["amount"] != amount
                    or prior["reason"] != payload.reason
                ):
                    fail("Cash movement request already used.", 409)
                return {"id": prior["id"]}
            if record["status"] != "open":
                fail("Till session is closed.", 409)
            total = await till_totals(c, tenant, record)
            if total["expected"] + amount < 0:
                fail("Cash out exceeds expected cash.", 409)
            mid = service.uid()
            await c.execute(
                "INSERT INTO till_cash_movements(id,tenant,session,request,amount,reason,actor) VALUES($1,$2,$3,$4,$5,$6,$7)",
                mid,
                tenant,
                identifier,
                payload.request,
                amount,
                payload.reason,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Till cash movement",
                {"id": mid, "amount": amount, "reason": payload.reason},
            )
    return {"id": mid}


@router.post("/tills/{identifier}/close")
async def close_till(
    tenant: str, identifier: str, payload: CloseTill, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            record = await c.fetchrow(
                "SELECT * FROM till_sessions WHERE tenant=$1 AND id=$2 AND actor=$3 FOR UPDATE",
                tenant,
                identifier,
                user["id"],
            )
            if not record:
                fail("Till session not found.", 404)
            if record["status"] == "closed":
                if (
                    record["counted_cash"] != payload.counted_cash
                    or record["closing_note"] != payload.note
                ):
                    fail("Till was closed with different counted cash or notes.", 409)
                return dict(record)
            total = await till_totals(c, tenant, record)
            variance = payload.counted_cash - total["expected"]
            if variance and not payload.note:
                fail("Explain the cash discrepancy before closing.")
            result = await c.fetchrow(
                "UPDATE till_sessions SET status='closed',closed=now(),expected_cash=$1,counted_cash=$2,variance=$3,closing_note=$4 WHERE id=$5 RETURNING *",
                total["expected"],
                payload.counted_cash,
                variance,
                payload.note,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Till closed",
                {
                    "id": identifier,
                    "expected": total["expected"],
                    "counted": payload.counted_cash,
                    "variance": variance,
                },
            )
    return dict(result)


@router.get("/customers/{identifier}")
async def get_customer(tenant: str, identifier: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit")
        record = await c.fetchrow(
            "SELECT * FROM customers WHERE tenant=$1 AND id=$2", tenant, identifier
        )
        if not record:
            fail("Customer not found.", 404)
    return dict(record)
