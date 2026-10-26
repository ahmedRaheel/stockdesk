"""Tenant tax configuration with effective dates and authoritative checkout quotes."""

from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator
from .contracts import Contract, Money, SaleLine, Identifier
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail
from ..features import taxation

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}",
    dependencies=[Depends(authenticated)],
    tags=["Tax configuration"],
)


class Profile(Contract):
    name: str = Field(min_length=1, max_length=100)
    name_ur: str = Field(default="", max_length=100)
    rate_bps: int = Field(strict=True, ge=0, le=10000)
    inclusive: bool = False
    active: bool = True
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("End date must follow start date.")
        return self


class Settings(Contract):
    mode: Literal["manual", "configured", "disabled"]
    default_profile: str | None = None


class Quote(Contract):
    auto_promotion: bool = Field(default=False, strict=True)
    customer_id: Identifier | None = None
    promotion_code: str = Field(default="", max_length=240)
    items: list[SaleLine] = Field(min_length=1, max_length=100)
    discount: Money = 0
    tax_bps: int = Field(default=0, strict=True, ge=0, le=10000)


@router.get("/tax-settings")
async def settings(tenant: str, user: User):
    async with db.pool.acquire() as c:
        t, _ = await service.authorize(c, user, tenant)
        return {
            "mode": t["tax_mode"],
            "default_profile": t["default_tax_profile"],
            "profiles": service.rows(
                await c.fetch(
                    "SELECT * FROM tax_profiles WHERE tenant=$1 ORDER BY name,id",
                    tenant,
                )
            ),
        }


@router.put("/tax-settings")
async def update_settings(tenant: str, payload: Settings, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "settings", lock=True)
            if payload.default_profile and not await c.fetchval(
                "SELECT 1 FROM tax_profiles WHERE tenant=$1 AND id=$2 AND active=true",
                tenant,
                payload.default_profile,
            ):
                fail("Active tax profile not found.")
            await c.execute(
                "UPDATE tenants SET tax_mode=$1,default_tax_profile=$2 WHERE id=$3",
                payload.mode,
                payload.default_profile,
                tenant,
            )
            await service.audit(
                c, tenant, user, "Tax settings updated", payload.model_dump()
            )
    return {"ok": True}


async def save(tenant, payload, request, user, identifier=None):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "settings", lock=True)
            if identifier and not await c.fetchval(
                "SELECT 1 FROM tax_profiles WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            ):
                fail("Tax profile not found.", 404)
            if not identifier:
                identifier = service.uid()
                await c.execute(
                    "INSERT INTO tax_profiles(id,tenant,name,rate_bps) VALUES($1,$2,$3,$4)",
                    identifier,
                    tenant,
                    payload.name,
                    payload.rate_bps,
                )
            await c.execute(
                "UPDATE tax_profiles SET name=$1,name_ur=$2,rate_bps=$3,inclusive=$4,active=$5,starts_on=$6,ends_on=$7 WHERE tenant=$8 AND id=$9",
                payload.name,
                payload.name_ur,
                payload.rate_bps,
                payload.inclusive,
                payload.active,
                payload.starts_on,
                payload.ends_on,
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Tax profile saved",
                {"id": identifier, **payload.model_dump(mode="json")},
            )
    return {"id": identifier}


@router.post("/tax-profiles", status_code=201)
async def create(tenant: str, payload: Profile, request: Request, user: User):
    return await save(tenant, payload, request, user)


@router.put("/tax-profiles/{identifier}")
async def edit(
    tenant: str, identifier: str, payload: Profile, request: Request, user: User
):
    return await save(tenant, payload, request, user, identifier)


@router.post("/sales/quote")
async def preview(tenant: str, payload: Quote, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "sale")
            return await taxation.preview(c, tenant, payload.model_dump())
