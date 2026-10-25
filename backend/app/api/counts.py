"""Physical counts with batch provenance, maker/checker approval and movement fences."""

import json
from decimal import Decimal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/stock-counts",
    dependencies=[Depends(authenticated)],
    tags=["Stock counts"],
)


class Create(Contract):
    request: Identifier
    reference: str = Field(min_length=1, max_length=150)
    products: list[Identifier] = Field(min_length=1, max_length=200)


class Line(Contract):
    batch: Identifier
    counted: Decimal = Field(ge=0, le=1_000_000_000, max_digits=12, decimal_places=3)


class Record(Contract):
    lines: list[Line] = Field(min_length=1, max_length=500)


class Decision(Contract):
    note: str = Field(min_length=1, max_length=500)


async def record(c, tenant, identifier):
    r = await c.fetchrow(
        "SELECT * FROM stock_counts WHERE tenant=$1 AND id=$2", tenant, identifier
    )
    if not r:
        fail("Stock count not found.", 404)
    return r


@router.get("")
async def listing(
    tenant: str,
    user: User,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "stock")
        return {
            "items": service.rows(
                await c.fetch(
                    "SELECT s.*,u.name AS counter_name FROM stock_counts s JOIN users u ON u.id=s.created_by WHERE tenant=$1 ORDER BY created DESC,id LIMIT $2 OFFSET $3",
                    tenant,
                    limit,
                    offset,
                )
            )
        }


@router.get("/{identifier}")
async def detail(tenant: str, identifier: str, user: User):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "stock")
            r = await record(c, tenant, identifier)
            lines = await c.fetch(
                "SELECT l.*,p.name,p.sku,p.stock_revision AS current_revision,b.lot,b.expires,b.stock AS current_stock,u.fractional FROM stock_count_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product JOIN stock_batches b ON b.tenant=l.tenant AND b.id=l.batch JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id WHERE l.tenant=$1 AND l.count_id=$2 ORDER BY p.name,p.id,b.expires NULLS LAST,b.id",
                tenant,
                identifier,
            )
            return {"count": dict(r), "lines": service.rows(lines)}


@router.post("", status_code=201)
async def create(tenant: str, payload: Create, request: Request, user: User):
    security.csrf(request)
    if len(set(payload.products)) != len(payload.products):
        fail("Select each product once.")
    signature = json.dumps(payload.model_dump(), sort_keys=True)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "stock", lock=True)
            prior = await c.fetchrow(
                "SELECT * FROM stock_counts WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if prior:
                if prior["signature"] != signature or prior["created_by"] != user["id"]:
                    fail("Count request identifier already used.", 409)
                return {"id": prior["id"]}
            batches = []
            for pid in payload.products:
                p = await c.fetchrow(
                    "SELECT * FROM products WHERE tenant=$1 AND id=$2 AND active=true",
                    tenant,
                    pid,
                )
                if not p:
                    fail("Active product not found.", 404)
                rows = await c.fetch(
                    "SELECT * FROM stock_batches WHERE tenant=$1 AND product=$2 ORDER BY id",
                    tenant,
                    pid,
                )
                if not rows:
                    fail(
                        "Product has no received batches. Receive stock before counting it."
                    )
                batches.extend((b, p["stock_revision"]) for b in rows)
            if len(batches) > 500:
                fail("Select fewer products; a count supports up to 500 batches.")
            identifier = service.uid()
            await c.execute(
                "INSERT INTO stock_counts(id,tenant,request,signature,reference,created_by) VALUES($1,$2,$3,$4,$5,$6)",
                identifier,
                tenant,
                payload.request,
                signature,
                payload.reference,
                user["id"],
            )
            for b, revision in batches:
                await c.execute(
                    "INSERT INTO stock_count_lines(tenant,count_id,product,batch,expected,revision) VALUES($1,$2,$3,$4,$5,$6)",
                    tenant,
                    identifier,
                    b["product"],
                    b["id"],
                    b["stock"],
                    revision,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Stock count opened",
                {"id": identifier, "products": payload.products},
            )
    return {"id": identifier}


@router.put("/{identifier}/lines")
async def quantities(
    tenant: str, identifier: str, payload: Record, request: Request, user: User
):
    security.csrf(request)
    if len({x.batch for x in payload.lines}) != len(payload.lines):
        fail("Duplicate batch in count.")
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "stock", lock=True)
            r = await record(c, tenant, identifier)
            if r["created_by"] != user["id"]:
                fail("Only the counter can edit this count.", 403)
            if r["status"] != "draft":
                fail("Only draft counts can be edited.", 409)
            for line in payload.lines:
                row = await c.fetchrow(
                    "SELECT l.*,u.fractional FROM stock_count_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id WHERE l.tenant=$1 AND l.count_id=$2 AND l.batch=$3",
                    tenant,
                    identifier,
                    line.batch,
                )
                if not row:
                    fail("Batch not found in count.", 404)
                if not row["fractional"] and line.counted != int(line.counted):
                    fail("This product requires whole quantities.")
                await c.execute(
                    "UPDATE stock_count_lines SET counted=$1 WHERE tenant=$2 AND count_id=$3 AND batch=$4",
                    line.counted,
                    tenant,
                    identifier,
                    line.batch,
                )
            await service.audit(
                c,
                tenant,
                user,
                "Stock count recorded",
                {"id": identifier, "lines": payload.model_dump(mode="json")["lines"]},
            )
    return {"ok": True}


@router.post("/{identifier}/submit")
async def submit(tenant: str, identifier: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "stock", lock=True)
            r = await record(c, tenant, identifier)
            if r["created_by"] != user["id"]:
                fail("Only the counter can submit this count.", 403)
            if r["status"] == "submitted":
                return {"ok": True}
            if r["status"] != "draft":
                fail("Only draft counts can be submitted.", 409)
            if await c.fetchval(
                "SELECT 1 FROM stock_count_lines WHERE tenant=$1 AND count_id=$2 AND counted IS NULL",
                tenant,
                identifier,
            ):
                fail("Record every batch before submitting.")
            await c.execute(
                "UPDATE stock_counts SET status='submitted',submitted=now() WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            await service.audit(
                c, tenant, user, "Stock count submitted", {"id": identifier}
            )
    return {"ok": True}


@router.post("/{identifier}/post")
async def post(
    tenant: str, identifier: str, payload: Decision, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            _, role = await service.authorize(c, user, tenant, "stock", lock=True)
            r = await record(c, tenant, identifier)
            if "count_approve" not in service.grants(role):
                fail("A manager must approve count adjustments.", 403)
            if r["created_by"] == user["id"]:
                fail("A different manager must approve this count.", 403)
            if r["status"] == "posted":
                return {"id": identifier, "replayed": True}
            if r["status"] != "submitted":
                fail("Submit the count before approval.", 409)
            lines = await c.fetch(
                "SELECT l.*,p.stock_revision,b.lot,b.expires FROM stock_count_lines l JOIN products p ON p.tenant=l.tenant AND p.id=l.product JOIN stock_batches b ON b.tenant=l.tenant AND b.id=l.batch WHERE l.tenant=$1 AND l.count_id=$2 ORDER BY p.id,b.id",
                tenant,
                identifier,
            )
            # Check every revision before writing any movement; posting multiple batches then increments it.
            if any(x["stock_revision"] != x["revision"] for x in lines):
                fail(
                    "Stock moved after the count opened. Cancel and recount the affected products.",
                    409,
                )
            for line in lines:
                delta = line["counted"] - line["expected"]
                if delta:
                    await c.execute(
                        "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,lot,expires,batch_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                        service.uid(),
                        tenant,
                        line["product"],
                        delta,
                        "IN" if delta > 0 else "OUT",
                        "Count " + r["reference"] + ": " + payload.note,
                        user["email"],
                        line["lot"],
                        line["expires"],
                        line["batch"] if delta < 0 else None,
                    )
            await c.execute(
                "UPDATE stock_counts SET status='posted',approved_by=$1,note=$2,posted=now() WHERE tenant=$3 AND id=$4",
                user["id"],
                payload.note,
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Stock count posted",
                {"id": identifier, "note": payload.note},
            )
    return {"id": identifier}


@router.post("/{identifier}/cancel")
async def cancel(
    tenant: str, identifier: str, payload: Decision, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            _, role = await service.authorize(c, user, tenant, "stock", lock=True)
            r = await record(c, tenant, identifier)
            if r["created_by"] != user["id"] and "count_approve" not in service.grants(
                role
            ):
                fail("Only the counter or manager can cancel.", 403)
            if r["status"] == "posted":
                fail("Posted counts cannot be cancelled.", 409)
            if r["status"] == "cancelled":
                return {"ok": True}
            await c.execute(
                "UPDATE stock_counts SET status='cancelled',note=$1 WHERE tenant=$2 AND id=$3",
                payload.note,
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Stock count cancelled",
                {"id": identifier, "note": payload.note},
            )
    return {"ok": True}
