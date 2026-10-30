"""Staff-run campaigns with frozen audiences and tenant-wide contact suppression."""

import hashlib
import json
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, service, security
from ..rules import business_date, fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/campaigns",
    dependencies=[Depends(authenticated)],
    tags=["Customer campaigns"],
)
Audience = Literal["all", "members"]


class Preview(Contract):
    audience: Audience


class Create(Preview):
    request: Identifier
    name: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    audience_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class Action(Contract):
    request: Identifier
    version: int = Field(strict=True, ge=1)
    action: Literal["completed", "cancelled"]
    note: str = Field(min_length=1, max_length=1000)


class Contact(Contract):
    request: Identifier
    version: int = Field(strict=True, ge=1)
    outcome: Literal[
        "contacted", "interested", "not_interested", "no_answer", "opted_out", "skipped"
    ]
    note: str = Field(min_length=1, max_length=1000)


async def audience_rows(c, tenant, audience):
    rows = service.rows(
        await c.fetch(
            """SELECT c.id,c.name,c.phone FROM customers c
        WHERE c.tenant=$1 AND c.active AND NOT EXISTS(SELECT 1 FROM campaign_optouts o WHERE o.tenant=c.tenant AND o.customer=c.id)
        AND ($2='all' OR EXISTS(SELECT 1 FROM customer_memberships m WHERE m.tenant=c.tenant AND m.customer=c.id AND m.status='active' AND m.valid_from<=$3 AND m.valid_until>=$3))
        ORDER BY c.id LIMIT 5001""",
            tenant,
            audience,
            business_date(),
        )
    )
    if len(rows) > 5000:
        fail("Campaign audience exceeds 5,000 customers. Select a smaller audience.")
    token = hashlib.sha256(
        json.dumps([tenant, audience, rows], sort_keys=True).encode()
    ).hexdigest()
    return rows, token


async def campaign(c, tenant, identifier):
    row = await c.fetchrow(
        "SELECT * FROM customer_campaigns WHERE tenant=$1 AND id=$2", tenant, identifier
    )
    if not row:
        fail("Campaign not found.", 404)
    return row


async def replay(c, tenant, user, payload, action):
    signature = json.dumps(
        [user["id"], action, payload.model_dump(mode="json")], sort_keys=True
    )
    row = await c.fetchrow(
        "SELECT campaign,signature FROM campaign_events WHERE tenant=$1 AND request=$2",
        tenant,
        payload.request,
    )
    if row and row["signature"] != signature:
        fail("Request ID already used for different campaign data.", 409)
    return signature, {"id": row["campaign"], "replayed": True} if row else None


async def record(
    c, tenant, user, identifier, payload, signature, kind, details, customer=None
):
    await c.execute(
        "INSERT INTO campaign_events(id,tenant,campaign,customer,request,signature,actor,kind,note,details) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)",
        service.uid(),
        tenant,
        identifier,
        customer,
        payload.request,
        signature,
        user["email"],
        kind,
        getattr(payload, "note", ""),
        json.dumps(details),
    )
    await service.audit(
        c, tenant, user, "Campaign " + kind, {"id": identifier, "customer": customer}
    )
    return {"id": identifier}


@router.post("/preview")
async def preview(tenant: str, payload: Preview, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "campaigns")
        rows, token = await audience_rows(c, tenant, payload.audience)
        return {"count": len(rows), "sample": rows[:10], "audience_token": token}


@router.post("", status_code=201)
async def create(tenant: str, payload: Create, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "campaigns", lock=True)
            signature, prior = await replay(c, tenant, user, payload, "create")
            if prior:
                return prior
            rows, token = await audience_rows(c, tenant, payload.audience)
            if token != payload.audience_token:
                fail("Audience changed. Preview again before starting.", 409)
            if not rows:
                fail("No eligible customers in this audience.")
            identifier = service.uid()
            await c.execute(
                "INSERT INTO customer_campaigns(id,tenant,name,message,audience) VALUES($1,$2,$3,$4,$5)",
                identifier,
                tenant,
                payload.name,
                payload.message,
                payload.audience,
            )
            await c.executemany(
                "INSERT INTO campaign_recipients(tenant,campaign,customer,name,phone) VALUES($1,$2,$3,$4,$5)",
                [(tenant, identifier, r["id"], r["name"], r["phone"]) for r in rows],
            )
            return await record(
                c,
                tenant,
                user,
                identifier,
                payload,
                signature,
                "started",
                {"count": len(rows), "audience": payload.audience},
            )


@router.get("")
async def listing(tenant: str, user: User, offset: int = Query(0, ge=0, le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "campaigns")
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT c.*,(SELECT COUNT(*) FROM campaign_recipients r WHERE r.tenant=c.tenant AND r.campaign=c.id) AS recipients FROM customer_campaigns c WHERE tenant=$1 ORDER BY created DESC,id LIMIT 30 OFFSET $2",
                    tenant,
                    offset,
                )
            )
        }


@router.get("/{identifier}")
async def detail(
    tenant: str, identifier: str, user: User, offset: int = Query(0, ge=0, le=1000000)
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "campaigns")
            row = await campaign(c, tenant, identifier)
            query = """FROM campaign_recipients r JOIN customers c ON c.tenant=r.tenant AND c.id=r.customer
              WHERE r.tenant=$1 AND r.campaign=$2"""
            recipients = await c.fetch(
                "SELECT r.*,c.active,EXISTS(SELECT 1 FROM campaign_optouts o WHERE o.tenant=r.tenant AND o.customer=r.customer) AS suppressed "
                + query
                + " ORDER BY r.name,r.customer LIMIT 30 OFFSET $3",
                tenant,
                identifier,
                offset,
            )
            counts = await c.fetch(
                "SELECT r.outcome,COUNT(*) AS total " + query + " GROUP BY r.outcome",
                tenant,
                identifier,
            )
            return {
                "campaign": dict(row),
                "items": service.rows(recipients),
                "counts": {r["outcome"]: r["total"] for r in counts},
            }


@router.post("/{identifier}/recipients/{customer}")
async def contact(
    tenant: str,
    identifier: str,
    customer: str,
    payload: Contact,
    request: Request,
    user: User,
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "campaigns", lock=True)
            row = await campaign(c, tenant, identifier)
            signature, prior = await replay(
                c, tenant, user, payload, "contact:" + identifier + ":" + customer
            )
            if prior:
                return prior
            if row["status"] != "active":
                fail("Only active campaigns can be changed.", 409)
            recipient = await c.fetchrow(
                "SELECT * FROM campaign_recipients WHERE tenant=$1 AND campaign=$2 AND customer=$3",
                tenant,
                identifier,
                customer,
            )
            if not recipient:
                fail("Campaign recipient not found.", 404)
            if recipient["version"] != payload.version:
                fail("Recipient changed. Reload before saving.", 409)
            suppressed = await c.fetchval(
                "SELECT 1 FROM campaign_optouts WHERE tenant=$1 AND customer=$2",
                tenant,
                customer,
            )
            active = await c.fetchval(
                "SELECT active FROM customers WHERE tenant=$1 AND id=$2",
                tenant,
                customer,
            )
            if (suppressed or not active) and payload.outcome not in (
                "skipped",
                "opted_out",
            ):
                fail(
                    "This customer is inactive or opted out. Record a skipped outcome.",
                    409,
                )
            if payload.outcome == "opted_out":
                await c.execute(
                    "INSERT INTO campaign_optouts(tenant,customer) VALUES($1,$2) ON CONFLICT DO NOTHING",
                    tenant,
                    customer,
                )
            await c.execute(
                "UPDATE campaign_recipients SET outcome=$1,version=version+1 WHERE tenant=$2 AND campaign=$3 AND customer=$4",
                payload.outcome,
                tenant,
                identifier,
                customer,
            )
            return await record(
                c,
                tenant,
                user,
                identifier,
                payload,
                signature,
                "contact",
                {
                    "previous": recipient["outcome"],
                    "outcome": payload.outcome,
                    "version": payload.version + 1,
                },
                customer,
            )


@router.post("/{identifier}/actions")
async def change(
    tenant: str, identifier: str, payload: Action, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "campaigns", lock=True)
            row = await campaign(c, tenant, identifier)
            signature, prior = await replay(
                c, tenant, user, payload, "action:" + identifier
            )
            if prior:
                return prior
            if row["status"] != "active" or row["version"] != payload.version:
                fail("Campaign changed or closed. Reload before saving.", 409)
            if payload.action == "completed" and await c.fetchval(
                "SELECT 1 FROM campaign_recipients WHERE tenant=$1 AND campaign=$2 AND outcome='pending' LIMIT 1",
                tenant,
                identifier,
            ):
                fail(
                    "Record an outcome or skip every pending recipient before completing.",
                    409,
                )
            await c.execute(
                "UPDATE customer_campaigns SET status=$1,version=version+1 WHERE tenant=$2 AND id=$3",
                payload.action,
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
                payload.action,
                {"version": payload.version + 1},
            )


@router.get("/{identifier}/history")
async def history(
    tenant: str, identifier: str, user: User, offset: int = Query(0, ge=0, le=1000000)
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "campaigns")
        await campaign(c, tenant, identifier)
        rows = service.rows(
            await c.fetch(
                "SELECT e.id,e.kind,e.note,e.details,e.actor,e.created,r.name AS customer_name FROM campaign_events e LEFT JOIN campaign_recipients r ON r.tenant=e.tenant AND r.campaign=e.campaign AND r.customer=e.customer WHERE e.tenant=$1 AND e.campaign=$2 ORDER BY e.created DESC,e.id DESC LIMIT 30 OFFSET $3",
                tenant,
                identifier,
                offset,
            )
        )
        for r in rows:
            if isinstance(r["details"], str):
                r["details"] = json.loads(r["details"])
        return {"items": rows}
