"""Staff follow-up workflow. Notes and promises never post financial entries."""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, Field, model_validator
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, security, service
from ..rules import ROLES, fail, grants, business_date

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/recovery-cases",
    dependencies=[Depends(authenticated)],
    tags=["Recovery follow-up"],
)


class Create(Contract):
    request: Identifier
    receivable: Identifier
    assigned_to: Identifier
    next_follow_up: AwareDatetime
    note: str = Field(min_length=1, max_length=2000)


class Update(Contract):
    request: Identifier
    version: int = Field(strict=True, ge=1)
    assigned_to: Identifier
    next_follow_up: AwareDatetime
    status: Literal["open", "closed", "cancelled"]
    note: str = Field(min_length=1, max_length=2000)


class Activity(Contract):
    request: Identifier
    version: int = Field(strict=True, ge=1)
    outcome: Literal["contacted", "no_answer", "visited", "disputed", "promise", "note"]
    note: str = Field(min_length=1, max_length=2000)
    next_follow_up: AwareDatetime
    promised_on: date | None = None
    promised_amount: int | None = Field(
        default=None, strict=True, gt=0, le=100_000_000_000
    )

    @model_validator(mode="after")
    def promise_fields(self):
        if self.outcome == "promise":
            if self.promised_on is None or self.promised_amount is None:
                raise ValueError("A promise requires a date and amount.")
        elif self.promised_on is not None or self.promised_amount is not None:
            raise ValueError("Promise fields are only allowed for a promise outcome.")
        return self


# Current grants decide who can receive assignments; custom-role names confer no rights.
CREDIT_ROLES = [name for name, permissions in ROLES.items() if "credit" in permissions]
AGENT_QUERY = """SELECT u.id,u.name FROM users u
 LEFT JOIN members m ON m.user_id=u.id AND m.tenant=$1
 LEFT JOIN tenant_roles r ON r.tenant=m.tenant AND r.id=m.custom_role_id
 WHERE u.active AND ((u.id=$2 AND $3) OR (m.active AND
 ((m.custom_role_id IS NULL AND m.role=ANY($4::text[])) OR
 (m.custom_role_id IS NOT NULL AND r.active AND EXISTS(SELECT 1 FROM tenant_role_permissions p WHERE p.tenant=m.tenant AND p.role_id=r.id AND p.permission='credit')))))"""


async def require_agent(c, tenant, identifier, user):
    if not await c.fetchval(
        AGENT_QUERY + " AND u.id=$5",
        tenant,
        user["id"],
        user["is_admin"],
        CREDIT_ROLES,
        identifier,
    ):
        fail("Choose an active recovery agent with customer credit access.")


def valid_time(value):
    now = datetime.now(timezone.utc)
    if value < datetime(2000, 1, 1, tzinfo=timezone.utc) or value > now + timedelta(
        days=366
    ):
        fail("Follow-up time must be from year 2000 through the next 366 days.")


async def invoice(c, tenant, receivable):
    row = await c.fetchrow(
        """SELECT r.*,COALESCE((SELECT SUM(l.amount) FROM customer_ledger l WHERE l.tenant=r.tenant AND l.receivable=r.id),0)::bigint AS balance
    FROM receivables r WHERE r.tenant=$1 AND r.id=$2""",
        tenant,
        receivable,
    )
    if not row:
        fail("Credit invoice not found.", 404)
    return row


def signature(user, action, payload):
    return json.dumps(
        {
            "actor": user["id"],
            "action": action,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def replay(c, tenant, request, fingerprint):
    old = await c.fetchrow(
        "SELECT case_id,version,signature FROM recovery_events WHERE tenant=$1 AND request=$2",
        tenant,
        request,
    )
    if not old:
        return None
    if old["signature"] != fingerprint:
        fail("Request ID has already been used with different recovery data.", 409)
    return {"id": old["case_id"], "version": old["version"], "replayed": True}


async def event(c, tenant, user, case_id, payload, kind, fingerprint, version, details):
    identifier = service.uid()
    for assignment in (details, details.get("before", {}), details.get("after", {})):
        if assignment.get("assigned_to"):
            assignment["agent_name"] = await c.fetchval(
                "SELECT name FROM users WHERE id=$1", assignment["assigned_to"]
            )
    await c.execute(
        "INSERT INTO recovery_events(id,tenant,case_id,request,signature,actor,kind,note,details,version) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)",
        identifier,
        tenant,
        case_id,
        payload.request,
        fingerprint,
        user["id"],
        kind,
        payload.note,
        json.dumps(details, default=str),
        version,
    )
    await service.audit(
        c,
        tenant,
        user,
        "Recovery follow-up recorded",
        {"id": case_id, "event": identifier, "kind": kind, "version": version},
    )
    return {"id": case_id, "version": version}


@router.get("/agents")
async def agents(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit_approve")
        rows = await c.fetch(
            AGENT_QUERY
            + " AND ($5='' OR strpos(lower(u.name),lower($5))>0) ORDER BY u.name,u.id LIMIT 50 OFFSET $6",
            tenant,
            user["id"],
            user["is_admin"],
            CREDIT_ROLES,
            q,
            offset,
        )
        return {"items": service.rows(rows)}


@router.post("", status_code=201)
async def create(tenant: str, payload: Create, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit_approve", lock=True)
            fingerprint = signature(user, "create", payload)
            old = await replay(c, tenant, payload.request, fingerprint)
            if old:
                return old
            valid_time(payload.next_follow_up)
            await require_agent(c, tenant, payload.assigned_to, user)
            debt = await invoice(c, tenant, payload.receivable)
            if debt["status"] != "open" or debt["balance"] <= 0:
                fail(
                    "Only an outstanding credit invoice can have an open recovery case.",
                    409,
                )
            if await c.fetchval(
                "SELECT 1 FROM recovery_cases WHERE tenant=$1 AND receivable=$2 AND status='open'",
                tenant,
                payload.receivable,
            ):
                fail("An open recovery case already exists for this invoice.", 409)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO recovery_cases(id,tenant,receivable,assigned_to,next_follow_up,created_by) VALUES($1,$2,$3,$4,$5,$6)",
                identifier,
                tenant,
                payload.receivable,
                payload.assigned_to,
                payload.next_follow_up,
                user["id"],
            )
            return await event(
                c,
                tenant,
                user,
                identifier,
                payload,
                "created",
                fingerprint,
                1,
                {
                    "assigned_to": payload.assigned_to,
                    "next_follow_up": payload.next_follow_up,
                    "status": "open",
                    "balance": debt["balance"],
                },
            )


BASE_QUERY = """WITH cases AS (
 SELECT k.*,r.customer,r.due_date AS invoice_due,r.status AS invoice_status,s.invoice_number,
 c.name AS customer_name,c.phone,u.name AS agent_name,(u.active AND (u.is_admin OR EXISTS(SELECT 1 FROM members m LEFT JOIN tenant_roles cr ON cr.tenant=m.tenant AND cr.id=m.custom_role_id WHERE m.tenant=k.tenant AND m.user_id=u.id AND m.active AND ((m.custom_role_id IS NULL AND m.role IN ('Owner','Manager','Cashier')) OR (m.custom_role_id IS NOT NULL AND cr.active AND EXISTS(SELECT 1 FROM tenant_role_permissions cp WHERE cp.tenant=m.tenant AND cp.role_id=cr.id AND cp.permission='credit')))))) AS agent_available,
 COALESCE((SELECT SUM(l.amount) FROM customer_ledger l WHERE l.tenant=k.tenant AND l.receivable=k.receivable),0)::bigint AS balance
 FROM recovery_cases k JOIN receivables r ON r.tenant=k.tenant AND r.id=k.receivable
 JOIN sales s ON s.tenant=r.tenant AND s.id=r.sale JOIN customers c ON c.tenant=r.tenant AND c.id=r.customer
 JOIN users u ON u.id=k.assigned_to WHERE k.tenant=$1
 AND (NOT $2 OR k.assigned_to=$3) AND ($4='' OR strpos(lower(c.name||' '||c.phone||' '||s.invoice_number||' '||u.name),lower($4))>0)
), classified AS (SELECT *,CASE WHEN status!='open' THEN status WHEN balance<=0 OR invoice_status!='open' THEN 'settled' WHEN next_follow_up<=now() THEN 'due' ELSE 'upcoming' END AS queue_status FROM cases) """


@router.get("")
async def listing(
    tenant: str,
    user: User,
    state: Literal["all", "due", "upcoming", "settled", "closed", "cancelled"] = "due",
    mine: bool = False,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            _, role = await service.authorize(c, user, tenant, "credit")
            args = (tenant, mine, user["id"], q)
            rows = await c.fetch(
                BASE_QUERY
                + "SELECT * FROM classified WHERE ($5='all' OR queue_status=$5) ORDER BY next_follow_up,id LIMIT 30 OFFSET $6",
                *args,
                state,
                offset,
            )
            counts = await c.fetch(
                BASE_QUERY
                + "SELECT queue_status,COUNT(*) AS total FROM classified GROUP BY queue_status",
                *args,
            )
            return {
                "items": service.rows(rows),
                "counts": {r["queue_status"]: r["total"] for r in counts},
                "can_manage": "credit_approve" in grants(role),
                "user_id": user["id"],
            }


@router.get("/{identifier}/history")
async def history(
    tenant: str, identifier: str, user: User, offset: int = Query(0, ge=0, le=1_000_000)
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "credit")
        if not await c.fetchval(
            "SELECT 1 FROM recovery_cases WHERE tenant=$1 AND id=$2", tenant, identifier
        ):
            fail("Recovery case not found.", 404)
        rows = service.rows(
            await c.fetch(
                "SELECT e.id,e.kind,e.note,e.details,e.version,e.created,u.name AS actor_name FROM recovery_events e JOIN users u ON u.id=e.actor WHERE e.tenant=$1 AND e.case_id=$2 ORDER BY e.created DESC,e.id DESC LIMIT 30 OFFSET $3",
                tenant,
                identifier,
                offset,
            )
        )
        for row in rows:
            row["details"] = (
                json.loads(row["details"])
                if isinstance(row["details"], str)
                else row["details"]
            )
        return {"items": rows}


async def get_case(c, tenant, identifier):
    row = await c.fetchrow(
        "SELECT * FROM recovery_cases WHERE tenant=$1 AND id=$2", tenant, identifier
    )
    if not row:
        fail("Recovery case not found.", 404)
    return row


@router.put("/{identifier}")
async def update(
    tenant: str, identifier: str, payload: Update, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "credit_approve", lock=True)
            row = await get_case(c, tenant, identifier)
            fingerprint = signature(user, "update:" + identifier, payload)
            old = await replay(c, tenant, payload.request, fingerprint)
            if old:
                return old
            if row["version"] != payload.version:
                fail("Recovery case changed. Reload before saving.", 409)
            valid_time(payload.next_follow_up)
            # Closing an inactive agent's case is allowed; assigning/reopening requires current access.
            if payload.status == "open" or payload.assigned_to != row["assigned_to"]:
                await require_agent(c, tenant, payload.assigned_to, user)
            if payload.status == "open":
                debt = await invoice(c, tenant, row["receivable"])
                if debt["balance"] <= 0 or debt["status"] != "open":
                    fail(
                        "Only an outstanding credit invoice can have an open recovery case.",
                        409,
                    )
                if await c.fetchval(
                    "SELECT 1 FROM recovery_cases WHERE tenant=$1 AND receivable=$2 AND status='open' AND id!=$3",
                    tenant,
                    row["receivable"],
                    identifier,
                ):
                    fail("An open recovery case already exists for this invoice.", 409)
            await c.execute(
                "UPDATE recovery_cases SET assigned_to=$1,next_follow_up=$2,status=$3,version=version+1,updated=now() WHERE tenant=$4 AND id=$5",
                payload.assigned_to,
                payload.next_follow_up,
                payload.status,
                tenant,
                identifier,
            )
            before = {
                key: row[key] for key in ("assigned_to", "next_follow_up", "status")
            }
            after = dict(
                assigned_to=payload.assigned_to,
                next_follow_up=payload.next_follow_up,
                status=payload.status,
            )
            return await event(
                c,
                tenant,
                user,
                identifier,
                payload,
                "updated",
                fingerprint,
                row["version"] + 1,
                {"before": before, "after": after},
            )


@router.post("/{identifier}/activities")
async def activity(
    tenant: str, identifier: str, payload: Activity, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            _, role = await service.authorize(c, user, tenant, "credit", lock=True)
            row = await get_case(c, tenant, identifier)
            if row["assigned_to"] != user["id"] and "credit_approve" not in grants(
                role
            ):
                fail(
                    "Only the assigned agent or a credit approver can record recovery activity.",
                    403,
                )
            fingerprint = signature(user, "activity:" + identifier, payload)
            old = await replay(c, tenant, payload.request, fingerprint)
            if old:
                return old
            if row["version"] != payload.version:
                fail("Recovery case changed. Reload before saving.", 409)
            debt = await invoice(c, tenant, row["receivable"])
            if (
                row["status"] != "open"
                or debt["balance"] <= 0
                or debt["status"] != "open"
            ):
                fail("This recovery case is closed or its invoice is settled.", 409)
            valid_time(payload.next_follow_up)
            if payload.outcome == "promise":
                if payload.promised_on < business_date():
                    fail("A new payment promise cannot be in the past.")
                if payload.promised_amount > debt["balance"]:
                    fail("Promised amount cannot exceed the current invoice balance.")
            await c.execute(
                "UPDATE recovery_cases SET next_follow_up=$1,version=version+1,updated=now() WHERE tenant=$2 AND id=$3",
                payload.next_follow_up,
                tenant,
                identifier,
            )
            return await event(
                c,
                tenant,
                user,
                identifier,
                payload,
                payload.outcome,
                fingerprint,
                row["version"] + 1,
                {
                    "assigned_to": row["assigned_to"],
                    "next_follow_up": payload.next_follow_up,
                    "previous_follow_up": row["next_follow_up"],
                    "promised_on": payload.promised_on,
                    "promised_amount": payload.promised_amount,
                    "balance": debt["balance"],
                },
            )
