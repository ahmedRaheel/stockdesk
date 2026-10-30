"""Staff-recorded feedback with immutable submissions and audited resolution."""

import json
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/feedback",
    dependencies=[Depends(authenticated)],
    tags=["Customer feedback"],
)


class Submit(Contract):
    request: Identifier
    invoice_number: str = Field(default="", max_length=100)
    rating: int = Field(strict=True, ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


class Resolve(Contract):
    version: int = Field(strict=True, ge=1)
    status: Literal["open", "resolved"]
    note: str = Field(min_length=1, max_length=2000)


@router.get("")
async def listing(
    tenant: str,
    user: User,
    status: Literal["all", "open", "resolved"] = "all",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "feedback")
            summary = dict(
                await c.fetchrow(
                    "SELECT count(*) AS total, count(*) FILTER(WHERE status='open') AS open, round(avg(rating),2) AS average FROM customer_feedback WHERE tenant=$1",
                    tenant,
                )
            )
            total = await c.fetchval(
                "SELECT count(*) FROM customer_feedback WHERE tenant=$1 AND ($2='all' OR status=$2)",
                tenant,
                status,
            )
            items = await c.fetch(
                "SELECT f.id,f.source,f.rating,f.comment,f.status,f.resolution,f.version,f.created,f.updated,f.created_by,f.updated_by,s.invoice_number FROM customer_feedback f LEFT JOIN sales s ON s.tenant=f.tenant AND s.id=f.sale WHERE f.tenant=$1 AND ($2='all' OR f.status=$2) ORDER BY f.created DESC,f.id LIMIT $3 OFFSET $4",
                tenant,
                status,
                limit,
                offset,
            )
    return dict(items=service.rows(items), total=total, summary=summary)


@router.post("", status_code=201)
async def submit(tenant: str, payload: Submit, request: Request, user: User):
    security.csrf(request)
    signature = json.dumps(payload.model_dump(exclude={"request"}), sort_keys=True)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "feedback", lock=True)
            prior = await c.fetchrow(
                "SELECT id,signature,created_by FROM customer_feedback WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if prior:
                if (
                    prior["signature"] != signature
                    or prior["created_by"] != user["email"]
                ):
                    fail("Submission ID already used for different feedback.", 409)
                return dict(id=prior["id"])
            sale = None
            if payload.invoice_number:
                sale = await c.fetchval(
                    "SELECT id FROM sales WHERE tenant=$1 AND invoice_number=$2",
                    tenant,
                    payload.invoice_number,
                )
                if not sale:
                    fail("Invoice not found in this business.", 404)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO customer_feedback(id,tenant,request,signature,sale,rating,comment,created_by,updated_by) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8)",
                identifier,
                tenant,
                payload.request,
                signature,
                sale,
                payload.rating,
                payload.comment,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Customer feedback recorded",
                dict(
                    id=identifier,
                    invoice_number=payload.invoice_number,
                    rating=payload.rating,
                ),
            )
    return dict(id=identifier)


@router.put("/{identifier}")
async def resolve(
    tenant: str, identifier: str, payload: Resolve, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "feedback", lock=True)
            old = await c.fetchrow(
                "SELECT status,version FROM customer_feedback WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not old:
                fail("Feedback not found.", 404)
            if old["version"] != payload.version:
                fail("Feedback changed. Refresh before saving.", 409)
            await c.execute(
                "UPDATE customer_feedback SET status=$3,resolution=$4,version=version+1,updated=now(),updated_by=$5 WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
                payload.status,
                payload.note,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Customer feedback updated",
                dict(id=identifier, previous=old["status"], **payload.model_dump()),
            )
    return dict(id=identifier, version=payload.version + 1)
