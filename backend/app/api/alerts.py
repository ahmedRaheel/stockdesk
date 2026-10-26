"""Inventory-only alerts; all mutations are authorized, audited and tenant-serialized."""

from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field, model_validator
from .contracts import Contract
from .router import User, authenticated
from .. import db, service, security, config
from ..rules import fail
from ..features.alerts import evaluate

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/alert-center",
    dependencies=[Depends(authenticated)],
    tags=["Inventory alerts"],
)


class Rule(Contract):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["low_stock", "stock_out", "expiry"]
    product: str | None = Field(default=None, min_length=1, max_length=100)
    threshold: Decimal | None = Field(
        default=None, ge=0, le=1_000_000_000, decimal_places=3
    )
    expiry_days: int = Field(default=30, strict=True, ge=0, le=365)
    severity: Literal["info", "warning", "critical"] = "warning"
    escalate_after_minutes: int | None = Field(
        default=None, strict=True, ge=1, le=10080
    )
    active: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if self.kind != "low_stock" and self.threshold is not None:
            raise ValueError("Only low-stock rules accept a quantity threshold.")
        if self.severity == "critical" and self.escalate_after_minutes is not None:
            raise ValueError("Critical alerts cannot be escalated further.")
        return self


class Update(Rule):
    version: int = Field(strict=True, ge=1)


class Acknowledge(Contract):
    note: str = Field(min_length=1, max_length=500)


@router.get("/rules")
async def rules(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "alerts")
        return dict(
            worker_enabled=config.ALERT_WORKER_ENABLED,
            items=service.rows(
                await c.fetch(
                    "SELECT r.*,p.name AS product_name,p.sku FROM inventory_alert_rules r LEFT JOIN products p ON p.tenant=r.tenant AND p.id=r.product WHERE r.tenant=$1 ORDER BY r.created,r.id",
                    tenant,
                )
            ),
        )


async def save(tenant, payload, request, user, id=None):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "alerts", lock=True)
            if payload.product and not await c.fetchval(
                "SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND ($3=false OR active)",
                tenant,
                payload.product,
                payload.active,
            ):
                fail("Active product not found.", 404)
            if await c.fetchval(
                "SELECT 1 FROM inventory_alert_rules WHERE tenant=$1 AND name=$2 AND ($3::text IS NULL OR id<>$3)",
                tenant,
                payload.name,
                id,
            ):
                fail("Alert rule name already exists.", 409)
            values = [
                payload.name,
                payload.kind,
                payload.product,
                payload.threshold,
                payload.expiry_days,
                payload.severity,
                payload.active,
                payload.escalate_after_minutes,
            ]
            if id:
                old = await c.fetchrow(
                    "SELECT * FROM inventory_alert_rules WHERE tenant=$1 AND id=$2",
                    tenant,
                    id,
                )
                if not old:
                    fail("Alert rule not found.", 404)
                if old["version"] != payload.version:
                    fail("Alert rule changed. Reload before saving.", 409)
                await c.execute(
                    "UPDATE inventory_alert_rules SET name=$1,kind=$2,product=$3,threshold=$4,expiry_days=$5,severity=$6,active=$7,escalate_after_minutes=$8,version=version+1,last_evaluated=NULL WHERE tenant=$9 AND id=$10",
                    *values,
                    tenant,
                    id,
                )
                # An edited rule starts a new episode; old acknowledgements do not suppress new conditions.
                await c.execute(
                    "UPDATE inventory_alerts SET status='resolved',resolved=now(),resolution='rule_changed' WHERE tenant=$1 AND rule=$2 AND status IN ('open','acknowledged')",
                    tenant,
                    id,
                )
            else:
                if (
                    await c.fetchval(
                        "SELECT count(*) FROM inventory_alert_rules WHERE tenant=$1",
                        tenant,
                    )
                    >= 50
                ):
                    fail("Maximum 50 alert rules per business.", 422)
                id = service.uid()
                await c.execute(
                    "INSERT INTO inventory_alert_rules(name,kind,product,threshold,expiry_days,severity,active,escalate_after_minutes,tenant,id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                    *values,
                    tenant,
                    id,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Inventory alert rule saved",
                dict(id=id, **payload.model_dump()),
            )
            return dict(id=id)


@router.post("/rules", status_code=201)
async def create(tenant: str, payload: Rule, request: Request, user: User):
    return await save(tenant, payload, request, user)


@router.put("/rules/{id}")
async def update(tenant: str, id: str, payload: Update, request: Request, user: User):
    return await save(tenant, payload, request, user, id)


@router.post("/evaluate")
async def refresh(tenant: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "alerts", lock=True)
            return await evaluate(c, tenant, user)


@router.get("")
async def inbox(
    tenant: str,
    user: User,
    status: Literal["open", "acknowledged", "resolved", "all"] = "open",
    escalated_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "alerts")
            clause = "tenant=$1 AND ($2='all' OR status=$2) AND ($3=false OR escalated_at IS NOT NULL)"
            total = await c.fetchval(
                "SELECT count(*) FROM inventory_alerts WHERE " + clause,
                tenant,
                status,
                escalated_only,
            )
            rows = service.rows(
                await c.fetch(
                    "SELECT * FROM inventory_alerts WHERE "
                    + clause
                    + " ORDER BY opened DESC,id LIMIT $4 OFFSET $5",
                    tenant,
                    status,
                    escalated_only,
                    limit,
                    offset,
                )
            )
    return dict(items=rows, total=total)


@router.post("/{id}/acknowledge")
async def acknowledge(
    tenant: str, id: str, payload: Acknowledge, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "alerts", lock=True)
            old = await c.fetchrow(
                "SELECT * FROM inventory_alerts WHERE tenant=$1 AND id=$2", tenant, id
            )
            if not old:
                fail("Alert not found.", 404)
            if old["status"] == "resolved":
                fail("This alert is already resolved.", 409)
            if old["status"] == "open":
                await c.execute(
                    "UPDATE inventory_alerts SET status='acknowledged',acknowledged=now(),acknowledged_by=$1,acknowledgement_note=$2 WHERE tenant=$3 AND id=$4",
                    user["email"],
                    payload.note,
                    tenant,
                    id,
                )
                await service.audit(
                    c,
                    tenant,
                    user,
                    "Inventory alert acknowledged",
                    dict(id=id, note=payload.note),
                )
    return dict(ok=True)
