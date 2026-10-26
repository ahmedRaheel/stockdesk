"""Tenant-scoped promotion administration and cashier code lookup."""

from datetime import date
from typing import Literal, Annotated
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field, model_validator
from .contracts import Contract, Identifier, Money, Quantity
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/promotions",
    dependencies=[Depends(authenticated)],
    tags=["Promotions"],
)


class Component(Contract):
    product: Identifier
    quantity: Quantity


class Promotion(Contract):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=150)
    name_ur: str = Field(default="", max_length=150)
    kind: Literal["fixed", "percentage", "bogo", "bundle", "cross_bogo"]
    reward_product: Identifier | None = None
    value: Money = 0
    minimum_subtotal: Money = 0
    maximum_discount: int | None = Field(
        default=None, strict=True, ge=1, le=100_000_000_000
    )
    buy_quantity: int = Field(default=1, strict=True, ge=1, le=1_000_000)
    free_quantity: int = Field(default=1, strict=True, ge=1, le=1_000_000)
    weekdays: list[Annotated[int, Field(strict=True, ge=0, le=6)]] = Field(
        default_factory=lambda: list(range(7)), min_length=1, max_length=7
    )
    starts_on: date | None = None
    ends_on: date | None = None
    starts_minute: int | None = Field(default=None, strict=True, ge=0, le=1439)
    ends_minute: int | None = Field(default=None, strict=True, ge=1, le=1440)
    usage_limit: int | None = Field(default=None, strict=True, ge=1, le=1_000_000_000)
    per_customer_limit: int | None = Field(
        default=None, strict=True, ge=1, le=1_000_000_000
    )
    active: bool = Field(default=True, strict=True)
    components: list[Component] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("End date must follow start date.")
        if (self.starts_minute is None) != (self.ends_minute is None) or (
            self.starts_minute is not None and self.ends_minute == self.starts_minute
        ):
            raise ValueError(
                "Choose both distinct start and end times; end is exclusive."
            )
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("Choose distinct weekdays.")
        if self.kind == "percentage" and not 1 <= self.value <= 10000:
            raise ValueError("Percentage rate must be 1–10000 basis points.")
        if self.kind == "fixed" and self.value <= 0:
            raise ValueError("Fixed discount must be positive.")
        if len({c.product for c in self.components}) != len(self.components):
            raise ValueError("Choose distinct component products.")
        if self.kind in {"fixed", "percentage"} and self.components:
            raise ValueError("Invoice discounts cannot have component products.")
        if self.kind == "bogo" and (
            len(self.components) != 1
            or self.components[0].quantity != 1
            or self.value != 0
        ):
            raise ValueError(
                "BOGO requires one product, component quantity 1 and value 0."
            )
        if self.kind == "cross_bogo":
            if (
                len(self.components) != 2
                or any(c.quantity != 1 for c in self.components)
                or self.value != 0
                or self.reward_product not in {c.product for c in self.components}
            ):
                raise ValueError(
                    "Cross-product BOGO requires two distinct products, component quantity 1, a selected reward product and value 0."
                )
        elif self.reward_product is not None:
            raise ValueError("Reward product applies only to cross-product BOGO.")
        if self.kind == "bundle" and len(self.components) < 2:
            raise ValueError("A bundle requires at least two distinct products.")
        return self


class Update(Promotion):
    version: int = Field(strict=True, ge=1)


@router.get("")
async def listing(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    include_inactive: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            _, role = await service.authorize(c, user, tenant)
            if "promotions" not in service.grants(role):
                await service.authorize(c, user, tenant, "sale")
                if include_inactive:
                    fail("Your role cannot perform this action.", 403)
            clause = "tenant=$1 AND ($2='' OR strpos(lower(code||' '||name||' '||name_ur),lower($2))>0) AND ($3 OR active=true)"
            total = await c.fetchval(
                "SELECT count(*) FROM promotions WHERE " + clause,
                tenant,
                q,
                include_inactive,
            )
            rows = service.rows(
                await c.fetch(
                    "SELECT p.*,(SELECT count(*) FROM promotion_redemptions r WHERE r.tenant=p.tenant AND r.promotion=p.id) AS used FROM promotions p WHERE "
                    + clause
                    + " ORDER BY code,id LIMIT $4 OFFSET $5",
                    tenant,
                    q,
                    include_inactive,
                    limit,
                    offset,
                )
            )
            items = service.rows(
                await c.fetch(
                    "SELECT i.*,p.name,p.sku FROM promotion_items i JOIN products p ON p.tenant=i.tenant AND p.id=i.product WHERE i.tenant=$1 AND i.promotion=ANY($2::text[]) ORDER BY i.product",
                    tenant,
                    [r["id"] for r in rows],
                )
            )
            for row in rows:
                row["components"] = [i for i in items if i["promotion"] == row["id"]]
    return dict(items=rows, total=total, limit=limit, offset=offset)


async def save(tenant, payload, request, user, identifier=None):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "promotions", lock=True)
            if identifier:
                old = await c.fetchrow(
                    "SELECT * FROM promotions WHERE tenant=$1 AND id=$2",
                    tenant,
                    identifier,
                )
                if not old:
                    fail("Promotion not found.", 404)
                if old["version"] != payload.version:
                    fail("Promotion changed. Reload before saving.", 409)
                if old["code"] != payload.code:
                    fail("Promotion code cannot be changed; create a new promotion.")
                used = await c.fetchval(
                    "SELECT count(*) FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2",
                    tenant,
                    identifier,
                )
                if payload.usage_limit is not None and payload.usage_limit < used:
                    fail("Usage limit cannot be less than existing redemptions.")
            else:
                identifier = service.uid()
            if payload.per_customer_limit is not None:
                highest = await c.fetchval(
                    "SELECT COALESCE(MAX(n),0) FROM (SELECT count(*) n FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2 AND customer IS NOT NULL GROUP BY customer) counts",
                    tenant,
                    identifier,
                )
                if payload.per_customer_limit < highest:
                    fail(
                        "Per-customer limit cannot be less than existing customer redemptions."
                    )
            for item in payload.components:
                p = await c.fetchrow(
                    "SELECT p.active,l.fractional FROM products p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id WHERE p.tenant=$1 AND p.id=$2",
                    tenant,
                    item.product,
                )
                if not p or (payload.active and not p["active"]):
                    fail("Choose active component products from this business.")
                if (
                    not p["fractional"]
                    and item.quantity != item.quantity.to_integral_value()
                ) or (payload.kind in {"bogo", "cross_bogo"} and p["fractional"]):
                    fail(
                        "BOGO requires a whole-unit product; component quantities must respect product units."
                    )
            values = payload.model_dump(exclude={"components", "version"})
            fields = list(
                values
            )  # Only model-declared field names form SQL identifiers.
            if not hasattr(payload, "version"):
                await c.execute(
                    "INSERT INTO promotions(id,tenant,"
                    + ",".join(fields)
                    + ") VALUES($1,$2,"
                    + ",".join("$" + str(i + 3) for i in range(len(fields)))
                    + ")",
                    identifier,
                    tenant,
                    *values.values(),
                )
            else:
                await c.execute(
                    "UPDATE promotions SET "
                    + ",".join(k + "=$" + str(i + 3) for i, k in enumerate(fields))
                    + ",version=version+1 WHERE tenant=$1 AND id=$2",
                    tenant,
                    identifier,
                    *values.values(),
                )
                await c.execute(
                    "DELETE FROM promotion_items WHERE tenant=$1 AND promotion=$2",
                    tenant,
                    identifier,
                )
            for item in payload.components:
                await c.execute(
                    "INSERT INTO promotion_items(tenant,promotion,product,quantity) VALUES($1,$2,$3,$4)",
                    tenant,
                    identifier,
                    item.product,
                    item.quantity,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Promotion saved",
                dict(id=identifier, **payload.model_dump(mode="json")),
            )
            version = await c.fetchval(
                "SELECT version FROM promotions WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
    return dict(id=identifier, version=version)


@router.post("", status_code=201)
async def create(tenant: str, payload: Promotion, request: Request, user: User):
    return await save(tenant, payload, request, user)


@router.put("/{identifier}")
async def update(
    tenant: str, identifier: str, payload: Update, request: Request, user: User
):
    return await save(tenant, payload, request, user, identifier)
