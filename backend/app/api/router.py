"""Headless resource API; legacy workspace endpoints remain compatible.

Reads are bounded. Mutations delegate to the same business rules used by POS,
so alternate clients cannot bypass permissions, stock validation or audit trails.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import APIKeyCookie, HTTPBearer
from .contracts import (
    Adjustment,
    Checkout,
    Credentials,
    ProductCreate,
    ProductUpdate,
    PurchaseCreate,
    ReceivePurchase,
    ReturnSale,
    SupplierCreate,
)
from .. import config, db, security, service
from ..features.purchasing import service as purchasing
from ..rules import email, fail

cookie_scheme = APIKeyCookie(name="stockdesk_session", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def authenticated(
    request: Request, cookie=Depends(cookie_scheme), bearer=Depends(bearer_scheme)
):
    async with db.pool.acquire() as connection:
        return await security.identity(connection, request)


User = Annotated[dict, Depends(authenticated)]
router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticated)])
auth_router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@auth_router.post("/token")
async def token_login(payload: Credentials, request: Request):
    """Issue an opaque expiring bearer token for trusted server/native clients.

    Browser clients should use HttpOnly cookie login. Token credentials are never
    saved to localStorage by the supplied UI. Account throttling is shared with UI.
    """
    if request.headers.get("origin") is not None:
        security.csrf(request)
    address = email(payload.email)
    async with db.pool.acquire() as connection:
        await security.login_limit(connection, "account:" + address)
        user = await connection.fetchrow("SELECT * FROM users WHERE email=$1", address)
        valid = await security.verify_password(
            payload.password, user["password_hash"] if user else security.DUMMY_HASH
        )
        if not user or not user["active"] or not valid:
            fail("Invalid email or password.", 401)
        await connection.execute(
            "DELETE FROM login_limits WHERE key=$1",
            security.digest("account:" + address),
        )
        token = await security.issue_token(connection, user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": config.SESSION_HOURS * 3600,
    }


@router.delete("/auth/token", tags=["Authentication"])
async def revoke_token(request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM sessions WHERE token_hash=$1",
            security.digest(security.credential(request)),
        )
    return {"ok": True}


async def write(request, user, tenant, payload, action, identifier=None):
    security.csrf(request)
    command = {**payload.model_dump(), "tenant": tenant, "action": action}
    if identifier is not None:
        command["id"] = identifier
    async with db.pool.acquire() as connection:
        async with connection.transaction():
            return await service.execute(connection, user, command)


@router.get("/tenants", tags=["Businesses"])
async def tenants(user: User):
    async with db.pool.acquire() as connection:
        result = (
            await connection.fetch(
                "SELECT id,name,currency,status FROM tenants ORDER BY name"
            )
            if user["is_admin"]
            else await connection.fetch(
                "SELECT t.id,t.name,t.currency,t.status FROM tenants t JOIN members m ON m.tenant=t.id WHERE m.user_id=$1 AND m.active=true ORDER BY t.name",
                user["id"],
            )
        )
    return {"items": service.rows(result)}


@router.get("/tenants/{tenant}/products", tags=["Catalog"])
async def products(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as connection:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(connection, user, tenant)
            # strpos treats percent/underscore as literal search characters.
            clause = "tenant=$1 AND ($2='' OR strpos(lower(name||' '||sku||' '||COALESCE(barcode,'')),lower($2))>0)"
            total = await connection.fetchval(
                "SELECT COUNT(*) FROM products WHERE " + clause, tenant, q
            )
            items = await connection.fetch(
                "SELECT * FROM products WHERE "
                + clause
                + " ORDER BY name,id LIMIT $3 OFFSET $4",
                tenant,
                q,
                limit,
                offset,
            )
    return {
        "items": service.rows(items),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tenants/{tenant}/products", tags=["Catalog"], status_code=201)
async def create_product(
    tenant: str, payload: ProductCreate, request: Request, user: User
):
    return await write(request, user, tenant, payload, "product")


@router.put("/tenants/{tenant}/products/{product_id}", tags=["Catalog"])
async def update_product(
    tenant: str, product_id: str, payload: ProductUpdate, request: Request, user: User
):
    return await write(request, user, tenant, payload, "editProduct", product_id)


@router.post("/tenants/{tenant}/stock-adjustments", tags=["Inventory"])
async def adjust_stock(tenant: str, payload: Adjustment, request: Request, user: User):
    return await write(request, user, tenant, payload, "movement")


@router.post("/tenants/{tenant}/sales", tags=["Sales"])
async def checkout(tenant: str, payload: Checkout, request: Request, user: User):
    return await write(request, user, tenant, payload, "checkout")


@router.get("/tenants/{tenant}/sales/{sale_id}", tags=["Sales"])
async def receipt(tenant: str, sale_id: str, user: User):
    async with db.pool.acquire() as connection:
        return await service.get_receipt(connection, user, tenant, sale_id)


@router.post("/tenants/{tenant}/sales/{sale_id}/returns", tags=["Sales"])
async def return_sale(
    tenant: str, sale_id: str, payload: ReturnSale, request: Request, user: User
):
    return await write(request, user, tenant, payload, "return", sale_id)


@router.get("/tenants/{tenant}/suppliers", tags=["Purchasing"])
async def suppliers(
    tenant: str,
    user: User,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as connection:
        await service.authorize(connection, user, tenant, "stock")
        items = await connection.fetch(
            "SELECT * FROM suppliers WHERE tenant=$1 ORDER BY name,id LIMIT $2 OFFSET $3",
            tenant,
            limit,
            offset,
        )
    return {"items": service.rows(items), "limit": limit, "offset": offset}


@router.post("/tenants/{tenant}/suppliers", tags=["Purchasing"], status_code=201)
async def add_supplier(
    tenant: str, payload: SupplierCreate, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as connection:
        async with connection.transaction():
            return await purchasing.add_supplier(
                connection, user, tenant, payload.model_dump()
            )


@router.get("/tenants/{tenant}/purchase-orders", tags=["Purchasing"])
async def purchases(
    tenant: str,
    user: User,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as connection:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(connection, user, tenant, "stock")
            orders = service.rows(
                await connection.fetch(
                    "SELECT o.*,s.name AS supplier_name FROM purchase_orders o JOIN suppliers s ON s.tenant=o.tenant AND s.id=o.supplier WHERE o.tenant=$1 ORDER BY o.created DESC,o.id LIMIT $2 OFFSET $3",
                    tenant,
                    limit,
                    offset,
                )
            )
            ids = [order["id"] for order in orders]
            lines = service.rows(
                await connection.fetch(
                    "SELECT l.*,p.name,p.sku FROM purchase_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product WHERE l.tenant=$1 AND l.purchase=ANY($2::text[]) ORDER BY p.name,p.id",
                    tenant,
                    ids,
                )
            )
    for order in orders:
        order.pop("signature", None)
        order["lines"] = [line for line in lines if line["purchase"] == order["id"]]
    return {"items": orders, "limit": limit, "offset": offset}


@router.post("/tenants/{tenant}/purchase-orders", tags=["Purchasing"])
async def create_purchase(
    tenant: str, payload: PurchaseCreate, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as connection:
        async with connection.transaction():
            return await purchasing.create_order(
                connection, user, tenant, payload.model_dump()
            )


@router.post(
    "/tenants/{tenant}/purchase-orders/{order_id}/receipts", tags=["Purchasing"]
)
async def receive_purchase(
    tenant: str, order_id: str, payload: ReceivePurchase, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as connection:
        async with connection.transaction():
            return await purchasing.receive_order(
                connection, user, tenant, order_id, payload.model_dump()
            )


@router.post("/tenants/{tenant}/purchase-orders/{order_id}/cancel", tags=["Purchasing"])
async def cancel_purchase(tenant: str, order_id: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as connection:
        async with connection.transaction():
            return await purchasing.cancel_order(connection, user, tenant, order_id)
