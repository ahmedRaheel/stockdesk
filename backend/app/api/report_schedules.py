import json
import hashlib
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .report_builder import Definition
from .. import db, service, security
from ..rules import fail
from ..features.report_scheduler import decoded, next_slot, worker_once

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/report-schedules",
    dependencies=[Depends(authenticated)],
    tags=["Scheduled reports"],
)


class Schedule(Contract):
    id: Identifier
    version: int = Field(strict=True, ge=0)
    name: str = Field(min_length=1, max_length=100)
    view: Identifier
    view_version: int = Field(strict=True, ge=1)
    frequency: Literal["daily", "weekly"]
    weekday: int = Field(default=0, strict=True, ge=0, le=6)
    hour: int = Field(strict=True, ge=0, le=23)
    minute: int = Field(default=0, strict=True, ge=0, le=59)
    active: bool = Field(default=True, strict=True)
    start_now: bool = Field(default=False, strict=True)


@router.put("")
async def save(tenant: str, payload: Schedule, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "cost", lock=True)
            signature = hashlib.sha256(
                json.dumps(
                    [user["id"], payload.model_dump(mode="json")], sort_keys=True
                ).encode()
            ).hexdigest()
            old = await c.fetchrow(
                "SELECT version,last_signature FROM report_schedules WHERE tenant=$1 AND id=$2",
                tenant,
                payload.id,
            )
            if (
                old
                and old["version"] == payload.version + 1
                and old["last_signature"] == signature
            ):
                return {"id": payload.id, "version": old["version"], "replayed": True}
            view = await c.fetchrow(
                "SELECT * FROM saved_report_views WHERE tenant=$1 AND id=$2",
                tenant,
                payload.view,
            )
            if not view:
                fail("Saved report not found.", 404)
            if view["version"] != payload.view_version:
                fail("Saved report changed. Reload before saving.", 409)
            definition = Definition(**decoded(view["definition"]))
            if definition.end is not None:
                fail("Schedules require a relative report view with a blank end date.")
            old = await c.fetchrow(
                "SELECT version FROM report_schedules WHERE tenant=$1 AND id=$2",
                tenant,
                payload.id,
            )
            if old and old["version"] != payload.version:
                fail("Schedule changed. Reload before saving.", 409)
            if not old and payload.version != 0:
                fail("Report schedule not found.", 404)
            if (
                not old
                and await c.fetchval(
                    "SELECT COUNT(*) FROM report_schedules WHERE tenant=$1", tenant
                )
                >= 50
            ):
                fail("A business can keep up to 50 report schedules.")
            now = await c.fetchval("SELECT now()")
            due = (
                now
                if payload.start_now
                else next_slot(
                    now,
                    payload.frequency,
                    payload.weekday,
                    payload.hour,
                    payload.minute,
                )
            )
            await c.execute(
                """INSERT INTO report_schedules(id,tenant,name,owner_id,definition,frequency,weekday,hour,minute,active,next_run,last_signature)
             VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11,$12)
             ON CONFLICT(id) DO UPDATE SET last_signature=excluded.last_signature,name=excluded.name,owner_id=excluded.owner_id,definition=excluded.definition,frequency=excluded.frequency,weekday=excluded.weekday,hour=excluded.hour,minute=excluded.minute,active=excluded.active,next_run=excluded.next_run,retry_after=NULL,version=report_schedules.version+1
             WHERE report_schedules.tenant=excluded.tenant""",
                payload.id,
                tenant,
                payload.name,
                user["id"],
                definition.model_dump_json(),
                payload.frequency,
                payload.weekday,
                payload.hour,
                payload.minute,
                payload.active,
                due,
                signature,
            )
            # Detect a global ID collision rather than reporting a successful foreign update.
            if not await c.fetchval(
                "SELECT 1 FROM report_schedules WHERE tenant=$1 AND id=$2",
                tenant,
                payload.id,
            ):
                fail("Schedule ID already exists. Create a new schedule.", 409)
            await c.execute(
                "UPDATE report_runs SET status='cancelled',error='Schedule changed before retry.',finished=now() WHERE tenant=$1 AND schedule=$2 AND status='retrying'",
                tenant,
                payload.id,
            )
            await service.audit(
                c, tenant, user, "Saved report schedule", payload.model_dump()
            )
            return {"id": payload.id, "version": payload.version + 1}


@router.get("")
async def listing(tenant: str, user: User):
    from .. import config

    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "cost")
        rows = service.rows(
            await c.fetch(
                "SELECT r.*,u.email AS owner_email FROM report_schedules r JOIN users u ON u.id=r.owner_id WHERE r.tenant=$1 ORDER BY r.name,r.id",
                tenant,
            )
        )
        for row in rows:
            row["definition"] = decoded(row["definition"])
            row.pop("last_signature", None)
        return {"items": rows, "worker_enabled": config.REPORT_WORKER_ENABLED}


@router.post("/evaluate")
async def evaluate(tenant: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "cost")
    return {"outcomes": await worker_once(tenant)}


@router.get("/runs")
async def runs(tenant: str, user: User, offset: int = Query(0, ge=0, le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "cost")
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT r.id,r.schedule,r.schedule_name AS name,r.owner_email,r.scheduled_for,r.status,r.attempts,r.error,r.created,r.finished FROM report_runs r WHERE r.tenant=$1 ORDER BY r.created DESC,r.id DESC LIMIT 30 OFFSET $2",
                    tenant,
                    offset,
                )
            )
        }


@router.get("/runs/{identifier}")
async def result(tenant: str, identifier: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "cost")
        row = await c.fetchrow(
            "SELECT * FROM report_runs WHERE tenant=$1 AND id=$2", tenant, identifier
        )
        if not row:
            fail("Report run not found.", 404)
        return {
            **dict(row),
            "definition": decoded(row["definition"]),
            "result": decoded(row["result"]),
        }


class Activation(Contract):
    version: int = Field(strict=True, ge=1)
    active: bool = Field(strict=True)


@router.post("/{identifier}/activation")
async def activation(
    tenant: str, identifier: str, payload: Activation, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "cost", lock=True)
            row = await c.fetchrow(
                "SELECT * FROM report_schedules WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not row:
                fail("Report schedule not found.", 404)
            if row["version"] != payload.version:
                fail("Schedule changed. Reload before saving.", 409)
            now = await c.fetchval("SELECT now()")
            due = next_slot(
                now, row["frequency"], row["weekday"], row["hour"], row["minute"]
            )
            await c.execute(
                "UPDATE report_schedules SET active=$1,owner_id=$2,next_run=$3,retry_after=NULL,version=version+1 WHERE tenant=$4 AND id=$5",
                payload.active,
                user["id"],
                due,
                tenant,
                identifier,
            )
            await c.execute(
                "UPDATE report_runs SET status='cancelled',error='Schedule changed before retry.',finished=now() WHERE tenant=$1 AND schedule=$2 AND status='retrying'",
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Report schedule activation",
                dict(id=identifier, active=payload.active),
            )
            return {"version": payload.version + 1}
