"""Owner-managed tenant roles, with bounded capabilities and immediate revocation."""

from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .router import User, authenticated
from .contracts import Contract, Identifier
from .. import db, service, security
from ..rules import ROLES, fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/roles",
    dependencies=[Depends(authenticated)],
    tags=["Custom roles"],
)
# Ownership, membership administration and role administration are not delegatable.
PERMISSIONS = {
    "promotions": "Manage promotions and coupon rules",
    "purchase_approve": "Approve another user’s purchase order",
    "supplier_return": "Return supplier goods and record credits",
    "read": "View catalog and stock",
    "sale": "Create sales and view receipts",
    "return": "Return whole sales",
    "credit": "Manage customer credit activity",
    "credit_approve": "Approve credit limits",
    "cost": "View costs and management reports",
    "product": "Create and edit products",
    "stock": "Purchasing and stock operations",
    "count_approve": "Approve another user’s stock count",
    "forecast": "View forecasts",
    "finance": "Manage supplier payables",
    "settings": "Business settings and reference data",
    "audit": "Read audit history",
}
DEPENDENCIES = {
    "purchase_approve": {"stock", "cost"},
    "supplier_return": {"stock", "finance", "cost"},
    "audit": {"cost"},
    "return": {"sale"},
    "credit_approve": {"credit"},
    "product": {"cost"},
    "stock": {"cost"},
    "forecast": {"cost"},
    "finance": {"cost"},
    "count_approve": {"stock", "cost"},
}


class Create(Contract):
    name: str = Field(min_length=1, max_length=80)
    name_ur: str = Field(default="", max_length=80)
    permissions: list[str] = Field(min_length=1, max_length=30)


class Update(Create):
    version: int = Field(strict=True, ge=1)
    active: bool = Field(strict=True)


class Assignment(Contract):
    member: Identifier
    role_id: Identifier


def validate(payload):
    if payload.name.casefold() in {x.casefold() for x in ROLES}:
        fail("Built-in role names are reserved.")
    selected = set(payload.permissions)
    if len(selected) != len(payload.permissions) or not selected.issubset(PERMISSIONS):
        fail("Select valid, distinct permissions.")
    if "read" not in selected:
        fail("Every role requires catalog read access.")
    for key, required in DEPENDENCIES.items():
        if key in selected and not required.issubset(selected):
            fail(f"{key} requires: " + ", ".join(sorted(required)))
    return selected


async def owner(c, u, t, lock=False):
    # `roles` is deliberately absent from the assignable permission catalog.
    await service.authorize(c, u, t, "roles", lock=lock)


@router.get("")
async def listing(tenant: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await owner(c, user, tenant)
            roles = service.rows(
                await c.fetch(
                    "SELECT r.*,(SELECT COUNT(*) FROM members m WHERE m.tenant=r.tenant AND m.custom_role_id=r.id) AS members FROM tenant_roles r WHERE tenant=$1 ORDER BY name,id",
                    tenant,
                )
            )
            for r in roles:
                r["permissions"] = [
                    x["permission"]
                    for x in await c.fetch(
                        "SELECT permission FROM tenant_role_permissions WHERE tenant=$1 AND role_id=$2 ORDER BY permission",
                        tenant,
                        r["id"],
                    )
                ]
            return {
                "items": roles,
                "permissions": PERMISSIONS,
                "dependencies": DEPENDENCIES,
                "builtins": {k: sorted(v) for k, v in ROLES.items()},
            }


@router.get("/members")
async def members(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        await owner(c, user, tenant)
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT m.id,m.role,m.custom_role_id,m.active,u.email,u.name,r.name AS custom_name FROM members m JOIN users u ON u.id=m.user_id LEFT JOIN tenant_roles r ON r.tenant=m.tenant AND r.id=m.custom_role_id WHERE m.tenant=$1 AND (u.email ILIKE '%'||$2||'%' OR u.name ILIKE '%'||$2||'%') ORDER BY u.email,m.id LIMIT 50 OFFSET $3",
                    tenant,
                    q,
                    offset,
                )
            )
        }


async def write(c, user, tenant, payload, identifier=None):
    selected = validate(payload)
    if await c.fetchval(
        "SELECT 1 FROM tenant_roles WHERE tenant=$1 AND lower(name)=lower($2) AND ($3::text IS NULL OR id<>$3)",
        tenant,
        payload.name,
        identifier,
    ):
        fail("Role name already exists.", 409)
    if identifier:
        prior = await c.fetchrow(
            "SELECT * FROM tenant_roles WHERE tenant=$1 AND id=$2", tenant, identifier
        )
        if not prior:
            fail("Role not found.", 404)
        if prior["version"] != payload.version:
            fail("Role changed. Reload before saving.", 409)
        await c.execute(
            "UPDATE tenant_roles SET name=$1,name_ur=$2,active=$3,version=version+1 WHERE tenant=$4 AND id=$5",
            payload.name,
            payload.name_ur,
            payload.active,
            tenant,
            identifier,
        )
        await c.execute(
            "DELETE FROM tenant_role_permissions WHERE tenant=$1 AND role_id=$2",
            tenant,
            identifier,
        )
    else:
        if (
            await c.fetchval(
                "SELECT COUNT(*) FROM tenant_roles WHERE tenant=$1", tenant
            )
            >= 100
        ):
            fail("Maximum 100 custom roles per business.")
        identifier = service.uid()
        await c.execute(
            "INSERT INTO tenant_roles(id,tenant,name,name_ur) VALUES($1,$2,$3,$4)",
            identifier,
            tenant,
            payload.name,
            payload.name_ur,
        )
    for permission in sorted(selected):
        await c.execute(
            "INSERT INTO tenant_role_permissions(tenant,role_id,permission) VALUES($1,$2,$3)",
            tenant,
            identifier,
            permission,
        )
    await service.audit(
        c, tenant, user, "Custom role saved", {"id": identifier, **payload.model_dump()}
    )
    return {"id": identifier}


@router.post("", status_code=201)
async def create(tenant: str, payload: Create, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await owner(c, user, tenant, True)
            return await write(c, user, tenant, payload)


@router.put("/{identifier}")
async def update(
    tenant: str, identifier: str, payload: Update, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await owner(c, user, tenant, True)
            return await write(c, user, tenant, payload, identifier)


@router.post("/assignments")
async def assign(tenant: str, payload: Assignment, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await owner(c, user, tenant, True)
            m = await c.fetchrow(
                "SELECT * FROM members WHERE tenant=$1 AND id=$2",
                tenant,
                payload.member,
            )
            if not m:
                fail("Member not found.", 404)
            if m["role"] == "Owner":
                fail("Owner membership cannot be replaced with a custom role.", 409)
            if not await c.fetchval(
                "SELECT 1 FROM tenant_roles WHERE tenant=$1 AND id=$2 AND active=true",
                tenant,
                payload.role_id,
            ):
                fail("Active role not found.", 404)
            # Existing inactive memberships stay inactive; assignment is not reactivation.
            await c.execute(
                "UPDATE members SET custom_role_id=$1 WHERE tenant=$2 AND id=$3",
                payload.role_id,
                tenant,
                payload.member,
            )
            await service.audit(
                c, tenant, user, "Custom role assigned", payload.model_dump()
            )
    return {"ok": True}
