"""Customer feedback through expiring, revocable bearer links, without staff sessions."""

import json
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from .contracts import Contract
from .router import User, authenticated
from .. import config, db, security, service
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/feedback/invitations",
    dependencies=[Depends(authenticated)],
    tags=["Customer feedback"],
)
public_router = APIRouter(
    prefix="/api/public/feedback", tags=["Customer feedback links"]
)
Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]


class Invite(Contract):
    invoice_number: str = Field(min_length=1, max_length=100)
    expires_days: int = Field(default=7, strict=True, ge=1, le=30)


class Access(Contract):
    token: Token


class Response(Access):
    rating: int = Field(strict=True, ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


@router.get("")
async def listing(
    tenant: str,
    user: User,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "feedback")
            total = await c.fetchval(
                "SELECT count(*) FROM feedback_invitations WHERE tenant=$1", tenant
            )
            items = await c.fetch(
                """SELECT i.id,s.invoice_number,i.created,i.created_by,i.expires,
                CASE WHEN i.revoked IS NOT NULL THEN 'revoked' WHEN i.submitted IS NOT NULL THEN 'submitted'
                  WHEN i.expires<=now() THEN 'expired' ELSE 'active' END AS status
                FROM feedback_invitations i JOIN sales s ON s.tenant=i.tenant AND s.id=i.sale
                WHERE i.tenant=$1 ORDER BY i.created DESC,i.id LIMIT $2 OFFSET $3""",
                tenant,
                limit,
                offset,
            )
    return dict(items=service.rows(items), total=total)


@router.post("", status_code=201)
async def create(tenant: str, payload: Invite, request: Request, user: User):
    security.csrf(request)
    token = secrets.token_urlsafe(32)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "feedback", lock=True)
            sale = await c.fetchval(
                "SELECT id FROM sales WHERE tenant=$1 AND invoice_number=$2",
                tenant,
                payload.invoice_number,
            )
            if not sale:
                fail("Invoice not found in this business.", 404)
            if await c.fetchval(
                "SELECT 1 FROM customer_feedback WHERE tenant=$1 AND sale=$2 AND source='customer'",
                tenant,
                sale,
            ):
                fail(
                    "Customer feedback has already been received for this invoice.", 409
                )
            # A replacement invalidates any outstanding link, including expired links.
            await c.execute(
                "UPDATE feedback_invitations SET revoked=now() WHERE tenant=$1 AND sale=$2 AND revoked IS NULL AND submitted IS NULL",
                tenant,
                sale,
            )
            identifier = service.uid()
            expires = await c.fetchval(
                """INSERT INTO feedback_invitations(id,tenant,sale,token_hash,expires,created_by)
                VALUES($1,$2,$3,$4,now()+($5::integer*interval '1 day'),$6) RETURNING expires""",
                identifier,
                tenant,
                sale,
                security.digest(token),
                payload.expires_days,
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Customer feedback link issued",
                dict(id=identifier, sale=sale, expires=expires.isoformat()),
            )
    return dict(
        id=identifier, expires=expires, url=config.APP_ORIGIN + "/feedback#" + token
    )


@router.post("/{identifier}/revoke")
async def revoke(tenant: str, identifier: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "feedback", lock=True)
            old = await c.fetchrow(
                "SELECT revoked,submitted FROM feedback_invitations WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not old:
                fail("Feedback link not found.", 404)
            if old["submitted"]:
                fail("This feedback link has already been used.", 409)
            if not old["revoked"]:
                await c.execute(
                    "UPDATE feedback_invitations SET revoked=now() WHERE tenant=$1 AND id=$2",
                    tenant,
                    identifier,
                )
                await service.audit(
                    c,
                    tenant,
                    user,
                    "Customer feedback link revoked",
                    dict(id=identifier),
                )
    return dict(ok=True)


def public_origin(request):
    # Public bearer links do not use staff Authorization or ambient session cookies.
    if request.headers.get("origin") != config.APP_ORIGIN:
        fail("Invalid request origin.", 403)


async def limited_invitation(c, token):
    # Persist attempts before the submission transaction, including rejected retries.
    # Unknown tokens never create rows, avoiding an attacker-controlled key registry.
    row = await c.fetchrow(
        """UPDATE feedback_invitations SET
        attempts=CASE WHEN window_start<now()-interval '1 minute' THEN 1 ELSE attempts+1 END,
        window_start=CASE WHEN window_start<now()-interval '1 minute' THEN now() ELSE window_start END
        WHERE token_hash=$1 RETURNING id,tenant,attempts""",
        security.digest(token),
    )
    if not row:
        fail("This feedback link is unavailable or has expired.", 404)
    if row["attempts"] > 30:
        fail("Too many feedback requests. Please try again in a minute.", 429)
    return row


async def available(c, reference, lock=False):
    # Staff revocation, issuance and submission share the tenant lock and lock order.
    business = await c.fetchrow(
        "SELECT name,status FROM tenants WHERE id=$1" + (" FOR UPDATE" if lock else ""),
        reference["tenant"],
    )
    invitation = await c.fetchrow(
        "SELECT *,expires>now() AS valid FROM feedback_invitations WHERE id=$1",
        reference["id"],
    )
    if (
        not business
        or not invitation
        or business["status"] != "active"
        or invitation["revoked"]
        or not invitation["valid"]
    ):
        fail("This feedback link is unavailable or has expired.", 404)
    return business, invitation


@public_router.post("/preview")
async def preview(payload: Access, request: Request):
    public_origin(request)
    async with db.pool.acquire() as c:
        reference = await limited_invitation(c, payload.token)
        async with c.transaction(isolation="repeatable_read", readonly=True):
            business, invitation = await available(c, reference)
            # No invoice, customer, payment, feedback text or staff data leaves this boundary.
            return dict(
                business_name=business["name"],
                expires=invitation["expires"],
                submitted=invitation["submitted"] is not None,
            )


@public_router.post("/submit")
async def submit(payload: Response, request: Request):
    public_origin(request)
    signature = json.dumps(
        dict(rating=payload.rating, comment=payload.comment), sort_keys=True
    )
    async with db.pool.acquire() as c:
        reference = await limited_invitation(c, payload.token)
        async with c.transaction():
            _, invitation = await available(c, reference, lock=True)
            if invitation["submitted"]:
                prior = await c.fetchval(
                    "SELECT signature FROM customer_feedback WHERE tenant=$1 AND id=$2",
                    reference["tenant"],
                    invitation["feedback"],
                )
                if prior != signature:
                    fail("Feedback has already been submitted using this link.", 409)
                return dict(submitted=True)
            identifier = service.uid()
            actor = "customer-link:" + invitation["id"]
            await c.execute(
                """INSERT INTO customer_feedback(id,tenant,request,signature,sale,rating,comment,created_by,updated_by,source)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8,'customer')""",
                identifier,
                reference["tenant"],
                "customer-link:" + invitation["id"],
                signature,
                invitation["sale"],
                payload.rating,
                payload.comment,
                actor,
            )
            await c.execute(
                "UPDATE feedback_invitations SET submitted=now(),feedback=$1 WHERE id=$2",
                identifier,
                invitation["id"],
            )
            await service.audit(
                c,
                reference["tenant"],
                dict(email=actor),
                "Customer feedback submitted",
                dict(id=identifier, invitation=invitation["id"], rating=payload.rating),
            )
    return dict(submitted=True)
