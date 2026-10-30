"""Bounded custom views over the existing sale-line margin report."""

import json
from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, model_validator
from .contracts import Contract, Identifier
from .router import User, authenticated
from .reports import report
from .. import db, service, security
from ..rules import business_date, fail
from ..features.report_exports import COLUMNS

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/report-builder",
    dependencies=[Depends(authenticated)],
    tags=["Custom reports"],
)


class Definition(Contract):
    group: Literal["products", "categories", "cashiers", "hours"] = "products"
    columns: list[str] = Field(min_length=1, max_length=11)
    days: int = Field(default=30, strict=True, ge=1, le=90)
    end: date | None = None
    search: str = Field(default="", max_length=100)
    hide_zero: bool = Field(default=False, strict=True)
    sort: str = "net_sales"
    descending: bool = Field(default=True, strict=True)
    limit: int = Field(default=100, strict=True, ge=1, le=5000)

    @model_validator(mode="after")
    def allowed_columns(self):
        allowed = {c[0] for c in COLUMNS[self.group]}
        if (
            len(set(self.columns)) != len(self.columns)
            or not set(self.columns) <= allowed
            or self.sort not in allowed
        ):
            raise ValueError(
                "Choose unique columns and a sort field from this report group."
            )
        return self


class Save(Contract):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    definition: Definition
    version: int = Field(strict=True, ge=0)


def build(data, definition):
    """Filters apply to aggregate rows, never to financial allocation inputs."""
    rows = data[definition.group]
    label_keys = {
        "products": ["sku", "name", "category"],
        "categories": ["category"],
        "cashiers": ["cashier"],
        "hours": ["hour"],
    }[definition.group]
    query = definition.search.casefold()
    rows = [
        r
        for r in rows
        if (not definition.hide_zero or r["net_sales"] != 0)
        and (
            not query
            or query in " ".join(str(r.get(k, "")) for k in label_keys).casefold()
        )
    ]
    # Stable source order breaks ties; null statistics always sort last.
    nonnull = [r for r in rows if r.get(definition.sort) is not None]
    nulls = [r for r in rows if r.get(definition.sort) is None]
    nonnull.sort(key=lambda r: r[definition.sort], reverse=definition.descending)
    visible = (nonnull + nulls)[: definition.limit]
    metadata = {
        key: {"key": key, "label": label, "kind": kind}
        for key, label, kind in COLUMNS[definition.group]
    }
    return {
        "columns": [metadata[k] for k in definition.columns],
        "rows": [{k: r.get(k) for k in definition.columns} for r in visible],
        "matching_rows": len(rows),
        "returned_rows": len(visible),
        "truncated": len(rows) > len(visible),
        "start": data["start"],
        "end": data["end"],
        "timezone": data["timezone"],
        "currency": data["currency"],
        "business": data["business"],
        "definition": definition.model_dump(mode="json"),
    }


@router.post("/run")
async def run(tenant: str, payload: Definition, request: Request, user: User):
    security.csrf(request)
    end = payload.end or business_date() - timedelta(days=1)
    if end >= business_date():
        fail("Report end must be a completed business day.")
    data = await report(tenant, user, payload.days, end=end)
    return build(data, payload)


@router.get("/views")
async def views(tenant: str, user: User, offset: int = Query(0, ge=0, le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "cost")
        rows = service.rows(
            await c.fetch(
                "SELECT id,name,definition,version,updated FROM saved_report_views WHERE tenant=$1 ORDER BY name,id LIMIT 30 OFFSET $2",
                tenant,
                offset,
            )
        )
        for row in rows:
            if isinstance(row["definition"], str):
                row["definition"] = json.loads(row["definition"])
        return {"items": rows}


@router.put("/views")
async def save(tenant: str, payload: Save, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "cost", lock=True)
            old = await c.fetchrow(
                "SELECT * FROM saved_report_views WHERE tenant=$1 AND id=$2",
                tenant,
                payload.id,
            )
            definition = payload.definition.model_dump(mode="json")
            if old:
                existing = (
                    json.loads(old["definition"])
                    if isinstance(old["definition"], str)
                    else old["definition"]
                )
                if (
                    old["version"] == payload.version + 1
                    and old["name"] == payload.name
                    and existing == definition
                ):
                    return {
                        "id": payload.id,
                        "version": old["version"],
                        "replayed": True,
                    }
                if old["version"] != payload.version:
                    fail("Saved report changed. Reload before saving.", 409)
                await c.execute(
                    "UPDATE saved_report_views SET name=$1,definition=$2::jsonb,version=version+1,updated=now() WHERE tenant=$3 AND id=$4",
                    payload.name,
                    json.dumps(definition),
                    tenant,
                    payload.id,
                )
            else:
                if payload.version != 0:
                    fail("Saved report not found.", 404)
                if (
                    await c.fetchval(
                        "SELECT COUNT(*) FROM saved_report_views WHERE tenant=$1",
                        tenant,
                    )
                    >= 100
                ):
                    fail("A business can save up to 100 report views.")
                await c.execute(
                    "INSERT INTO saved_report_views(id,tenant,name,definition,created_by) VALUES($1,$2,$3,$4::jsonb,$5)",
                    payload.id,
                    tenant,
                    payload.name,
                    json.dumps(definition),
                    user["email"],
                )
            await service.audit(
                c,
                tenant,
                user,
                "Saved report view",
                {"id": payload.id, "name": payload.name, "definition": definition},
            )
            return {"id": payload.id, "version": payload.version + 1}


@router.delete("/views/{identifier}")
async def remove(
    tenant: str,
    identifier: str,
    request: Request,
    user: User,
    version: int = Query(..., ge=1),
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "cost", lock=True)
            old = await c.fetchrow(
                "SELECT version FROM saved_report_views WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not old:
                return {"deleted": True}
            if old["version"] != version:
                fail("Saved report changed. Reload before saving.", 409)
            await c.execute(
                "DELETE FROM saved_report_views WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            await service.audit(
                c, tenant, user, "Deleted report view", {"id": identifier}
            )
            return {"deleted": True}
