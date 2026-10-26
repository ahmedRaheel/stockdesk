"""Password-enrolled cashier PINs; switched sessions never inherit other tenants/roles."""

import asyncio
from fastapi import APIRouter, Request, Response
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User
from .. import db, security, service
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/cashiers", tags=["Cashier switching"]
)


class PinSetup(Contract):
    password: str = Field(min_length=12, max_length=128)
    pin: str = Field(pattern=r"^[0-9]{6,12}$")


class PinSwitch(Contract):
    user_id: Identifier
    pin: str = Field(pattern=r"^[0-9]{6,12}$")


async def eligible(c, tenant, user_id):
    return await c.fetchrow(
        "SELECT u.*,p.pin_hash,p.revision FROM users u JOIN members m ON m.user_id=u.id LEFT JOIN cashier_pins p ON p.tenant=m.tenant AND p.user_id=u.id WHERE m.tenant=$1 AND u.id=$2 AND m.active AND u.active AND NOT u.is_admin AND m.role='Cashier' AND m.custom_role_id IS NULL",
        tenant,
        user_id,
    )


@router.get("")
async def roster(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "sale")
        rows = await c.fetch(
            "SELECT u.id,u.name,(p.user_id IS NOT NULL) AS pin_enabled FROM users u JOIN members m ON m.user_id=u.id LEFT JOIN cashier_pins p ON p.tenant=m.tenant AND p.user_id=u.id WHERE m.tenant=$1 AND m.active AND u.active AND NOT u.is_admin AND m.role='Cashier' AND m.custom_role_id IS NULL ORDER BY u.name,u.id",
            tenant,
        )
    return {"items": service.rows(rows)}


@router.put("/pin")
async def setup(tenant: str, body: PinSetup, request: Request, user: User):
    security.csrf(request)
    if user.get("tenant_scope"):
        fail("Sign in with your password before changing a cashier PIN.", 403)
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "sale")
        # Persist failed attempt counters outside the mutation transaction.
        await security.login_limit(c, "pin-setup:" + user["id"])
        if not await security.verify_password(body.password, user["password_hash"]):
            fail("Current password is incorrect.", 403)
        hashed = await asyncio.to_thread(security.ph.hash, body.pin)
        async with c.transaction():
            await service.authorize(c, user, tenant, "sale", lock=True)
            await security.identity(c, request)
            if not await eligible(c, tenant, user["id"]):
                fail(
                    "PIN switching is available only to built-in Cashier accounts.", 403
                )
            await c.execute(
                "INSERT INTO cashier_pins(tenant,user_id,pin_hash) VALUES($1,$2,$3) ON CONFLICT(tenant,user_id) DO UPDATE SET pin_hash=excluded.pin_hash,revision=cashier_pins.revision+1,updated=now()",
                tenant,
                user["id"],
                hashed,
            )
            await c.execute(
                "DELETE FROM sessions WHERE user_id=$1 AND tenant_scope=$2",
                user["id"],
                tenant,
            )
            await service.audit(
                c, tenant, user, "Cashier PIN updated", {"user_id": user["id"]}
            )
    return {"ok": True}


@router.delete("/{user_id}/pin")
async def revoke(tenant: str, user_id: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(
                c, user, tenant, "sale" if user_id == user["id"] else "team", lock=True
            )
            if user_id == user["id"] and user.get("tenant_scope"):
                fail("Sign in with your password before changing a cashier PIN.", 403)
            await c.execute(
                "DELETE FROM cashier_pins WHERE tenant=$1 AND user_id=$2",
                tenant,
                user_id,
            )
            await c.execute(
                "DELETE FROM sessions WHERE tenant_scope=$1 AND user_id=$2",
                tenant,
                user_id,
            )
            await service.audit(
                c, tenant, user, "Cashier PIN revoked", {"user_id": user_id}
            )
    return {"ok": True}


@router.post("/switch")
async def switch(
    tenant: str, body: PinSwitch, request: Request, response: Response, user: User
):
    security.csrf(request)
    if request.headers.get("authorization") is not None:
        fail("Cashier switching requires a browser session.", 400)
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "sale")
        await security.login_limit(c, "pin-source:" + user["id"])
        await security.login_limit(c, "pin-target:" + tenant + ":" + body.user_id)
        async with c.transaction():
            # Recheck the initiating credential after waiting for the tenant lock.
            await service.authorize(c, user, tenant, "sale", lock=True)
            await security.identity(c, request)
            target = await eligible(c, tenant, body.user_id)
            valid = await security.verify_password(
                body.pin,
                (
                    target["pin_hash"]
                    if target and target["pin_hash"]
                    else security.DUMMY_HASH
                ),
            )
            if not target or not target["pin_hash"] or not valid:
                fail("Cashier or PIN is incorrect.", 401)
            await c.execute(
                "DELETE FROM sessions WHERE token_hash=$1",
                security.digest(security.credential(request)),
            )
            await security.session(
                c, target["id"], response, tenant, target["revision"]
            )
            await c.execute(
                "DELETE FROM login_limits WHERE key=ANY($1::text[])",
                [
                    security.digest("pin-source:" + user["id"]),
                    security.digest("pin-target:" + tenant + ":" + target["id"]),
                ],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Cashier switched",
                {"from_user": user["id"], "to_user": target["id"]},
            )
    return {
        "user": service.public_user({**dict(target), "tenant_scope": tenant}),
        "tenant": tenant,
    }
