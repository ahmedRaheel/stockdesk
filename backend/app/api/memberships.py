"""Date-bound customer memberships. No payment or automatic pricing side effects."""

import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from typing import Literal
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail, business_date

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/memberships",
    dependencies=[Depends(authenticated)],
    tags=["Customer memberships"],
)


class Plan(Contract):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    duration_days: int = Field(strict=True, ge=1, le=730)
    benefits: str = Field(default="", max_length=2000)
    active: bool = Field(default=True, strict=True)


class PlanUpdate(Plan):
    version: int = Field(strict=True, ge=1)


class Enroll(Contract):
    request: Identifier
    customer: Identifier
    plan: Identifier
    plan_version: int = Field(strict=True, ge=1)
    valid_from: date
    note: str = Field(min_length=1, max_length=1000)


class Change(Contract):
    request: Identifier
    version: int = Field(strict=True, ge=1)
    action: Literal["renew", "cancel"]
    note: str = Field(min_length=1, max_length=1000)


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


@router.get("/plans")
async def plans(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "memberships")
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT * FROM membership_plans WHERE tenant=$1 AND ($2='' OR strpos(lower(name||' '||code),lower($2))>0) ORDER BY name,id LIMIT 50 OFFSET $3",
                    tenant,
                    q,
                    offset,
                )
            )
        }


async def write_plan(c, tenant, user, payload, identifier=None):
    if identifier:
        old = await c.fetchrow(
            "SELECT * FROM membership_plans WHERE tenant=$1 AND id=$2",
            tenant,
            identifier,
        )
        if not old:
            fail("Membership plan not found.", 404)
        if old["version"] != payload.version:
            fail("Membership plan changed. Reload before saving.", 409)
        if old["code"] != payload.code:
            fail("A membership plan code cannot be changed.")
        await c.execute(
            "UPDATE membership_plans SET name=$1,duration_days=$2,benefits=$3,active=$4,version=version+1 WHERE tenant=$5 AND id=$6",
            payload.name,
            payload.duration_days,
            payload.benefits,
            payload.active,
            tenant,
            identifier,
        )
    else:
        identifier = service.uid()
        await c.execute(
            "INSERT INTO membership_plans(id,tenant,code,name,duration_days,benefits,active) VALUES($1,$2,$3,$4,$5,$6,$7)",
            identifier,
            tenant,
            payload.code,
            payload.name,
            payload.duration_days,
            payload.benefits,
            payload.active,
        )
    await service.audit(
        c,
        tenant,
        user,
        "Membership plan saved",
        {"id": identifier, **payload.model_dump()},
    )
    return {"id": identifier}


@router.post("/plans", status_code=201)
async def create_plan(tenant: str, payload: Plan, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "memberships", lock=True)
            return await write_plan(c, tenant, user, payload)


@router.put("/plans/{identifier}")
async def update_plan(
    tenant: str, identifier: str, payload: PlanUpdate, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "memberships", lock=True)
            return await write_plan(c, tenant, user, payload, identifier)


async def overlap(c, tenant, customer, start, end, exclude=""):
    if await c.fetchval(
        "SELECT 1 FROM customer_memberships WHERE tenant=$1 AND customer=$2 AND status='active' AND valid_from<=$4 AND valid_until>=$3 AND id!=$5",
        tenant,
        customer,
        start,
        end,
        exclude,
    ):
        fail("This customer already has a membership covering those dates.", 409)


def fingerprint(user, action, payload):
    return json.dumps(
        {
            "actor": user["id"],
            "action": action,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
    )


async def replay(c, tenant, payload, signature):
    prior = await c.fetchrow(
        "SELECT membership,version,signature FROM membership_events WHERE tenant=$1 AND request=$2",
        tenant,
        payload.request,
    )
    if prior:
        if prior["signature"] != signature:
            fail("Request ID already used for different membership data.", 409)
        return {
            "id": prior["membership"],
            "version": prior["version"],
            "replayed": True,
        }


async def record(
    c, tenant, user, identifier, payload, signature, kind, version, details
):
    await c.execute(
        "INSERT INTO membership_events(id,tenant,membership,request,signature,actor,kind,note,details,version) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)",
        service.uid(),
        tenant,
        identifier,
        payload.request,
        signature,
        user["email"],
        kind,
        payload.note,
        json.dumps(details, default=str),
        version,
    )
    await service.audit(
        c,
        tenant,
        user,
        "Customer membership " + kind,
        {"id": identifier, "version": version},
    )
    return {"id": identifier, "version": version}


@router.post("", status_code=201)
async def enroll(tenant: str, payload: Enroll, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "memberships", lock=True)
            signature = fingerprint(user, "enroll", payload)
            previous = await replay(c, tenant, payload, signature)
            if previous:
                return previous
            today = business_date()
            if not today <= payload.valid_from <= today + timedelta(days=366):
                fail("Start date must be today or within the next 366 days.")
            if not await c.fetchval(
                "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active",
                tenant,
                payload.customer,
            ):
                fail("Active customer not found.", 404)
            plan = await c.fetchrow(
                "SELECT * FROM membership_plans WHERE tenant=$1 AND id=$2",
                tenant,
                payload.plan,
            )
            if not plan:
                fail("Membership plan not found.", 404)
            if not plan["active"] or plan["version"] != payload.plan_version:
                fail(
                    "Membership plan changed or is inactive. Reload before enrolling.",
                    409,
                )
            end = payload.valid_from + timedelta(days=plan["duration_days"] - 1)
            await overlap(c, tenant, payload.customer, payload.valid_from, end)
            number = await c.fetchval(
                "INSERT INTO membership_sequences(tenant,last_number) VALUES($1,1) ON CONFLICT(tenant) DO UPDATE SET last_number=membership_sequences.last_number+1 RETURNING last_number",
                tenant,
            )
            snapshot = {
                k: plan[k]
                for k in ("code", "name", "duration_days", "benefits", "version")
            }
            identifier = service.uid()
            await c.execute(
                "INSERT INTO customer_memberships(id,tenant,customer,plan,number,plan_snapshot,valid_from,valid_until) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8)",
                identifier,
                tenant,
                payload.customer,
                payload.plan,
                f"MEM-{number:06d}",
                json.dumps(snapshot),
                payload.valid_from,
                end,
            )
            return await record(
                c,
                tenant,
                user,
                identifier,
                payload,
                signature,
                "enrolled",
                1,
                {
                    "plan": snapshot,
                    "valid_from": payload.valid_from,
                    "valid_until": end,
                },
            )


@router.post("/{identifier}/actions")
async def change(
    tenant: str, identifier: str, payload: Change, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "memberships", lock=True)
            row = await c.fetchrow(
                "SELECT * FROM customer_memberships WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not row:
                fail("Membership not found.", 404)
            signature = fingerprint(user, "change:" + identifier, payload)
            previous = await replay(c, tenant, payload, signature)
            if previous:
                return previous
            if row["version"] != payload.version:
                fail("Membership changed. Reload before saving.", 409)
            if row["status"] == "cancelled":
                fail("A cancelled membership cannot be renewed. Enroll again.", 409)
            start, end = row["valid_from"], row["valid_until"]
            if payload.action == "renew":
                if not await c.fetchval(
                    "SELECT 1 FROM membership_plans WHERE tenant=$1 AND id=$2 AND active",
                    tenant,
                    row["plan"],
                ):
                    fail("Inactive membership plans cannot be renewed.", 409)
                if not await c.fetchval(
                    "SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active",
                    tenant,
                    row["customer"],
                ):
                    fail("Active customer not found.", 404)
                today = business_date()
                duration = decoded(row["plan_snapshot"])["duration_days"]
                term_start = max(today, end + timedelta(days=1))
                start = start if end >= today else today
                end = term_start + timedelta(days=duration - 1)
                if end > today + timedelta(days=3660):
                    fail("Membership coverage cannot extend more than ten years ahead.")
                await overlap(c, tenant, row["customer"], start, end, identifier)
            status = "cancelled" if payload.action == "cancel" else "active"
            await c.execute(
                "UPDATE customer_memberships SET valid_from=$1,valid_until=$2,status=$3,version=version+1,updated=now() WHERE tenant=$4 AND id=$5",
                start,
                end,
                status,
                tenant,
                identifier,
            )
            return await record(
                c,
                tenant,
                user,
                identifier,
                payload,
                signature,
                "cancelled" if payload.action == "cancel" else "renewed",
                row["version"] + 1,
                {
                    "previous_from": row["valid_from"],
                    "previous_until": row["valid_until"],
                    "valid_from": start,
                    "valid_until": end,
                    "status": status,
                },
            )


@router.get("")
async def listing(
    tenant: str,
    user: User,
    state: Literal["all", "active", "scheduled", "expired", "cancelled"] = "all",
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "memberships")
            query = """WITH members AS (SELECT m.*,c.name AS customer_name,c.phone,CASE WHEN m.status='cancelled' THEN 'cancelled' WHEN valid_from>$2 THEN 'scheduled' WHEN valid_until<$2 THEN 'expired' ELSE 'active' END AS membership_status FROM customer_memberships m JOIN customers c ON c.tenant=m.tenant AND c.id=m.customer WHERE m.tenant=$1 AND ($3='' OR strpos(lower(m.number||' '||c.name||' '||c.phone||' '||(m.plan_snapshot->>'name')),lower($3))>0)) """
            args = (tenant, business_date(), q)
            rows = service.rows(
                await c.fetch(
                    query
                    + "SELECT * FROM members WHERE ($4='all' OR membership_status=$4) ORDER BY created DESC,id LIMIT 30 OFFSET $5",
                    *args,
                    state,
                    offset,
                )
            )
            counts = await c.fetch(
                query
                + "SELECT membership_status,COUNT(*) AS total FROM members GROUP BY membership_status",
                *args,
            )
            for row in rows:
                row["plan_snapshot"] = decoded(row["plan_snapshot"])
            return {
                "items": rows,
                "counts": {r["membership_status"]: r["total"] for r in counts},
                "as_of": business_date(),
            }


@router.get("/{identifier}/history")
async def history(
    tenant: str, identifier: str, user: User, offset: int = Query(0, ge=0, le=1000000)
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "memberships")
        if not await c.fetchval(
            "SELECT 1 FROM customer_memberships WHERE tenant=$1 AND id=$2",
            tenant,
            identifier,
        ):
            fail("Membership not found.", 404)
        rows = service.rows(
            await c.fetch(
                "SELECT kind,note,details,version,actor,created FROM membership_events WHERE tenant=$1 AND membership=$2 ORDER BY version DESC LIMIT 30 OFFSET $3",
                tenant,
                identifier,
                offset,
            )
        )
        for row in rows:
            row["details"] = decoded(row["details"])
        return {"items": rows}
