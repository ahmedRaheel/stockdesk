"""Small atomic CSV imports. Preview exercises the real write rules in a rollback."""

import csv, io, json, hashlib
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import Field, ValidationError
from .contracts import Contract, Identifier, ProductCreate
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail
from ..features.catalog import save_product

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/catalog-imports",
    dependencies=[Depends(authenticated)],
    tags=["Catalog imports"],
)
COLUMNS = [
    "sku",
    "name",
    "category_code",
    "unit_code",
    "barcode",
    "price",
    "cost",
    "initial",
    "reorder",
]


class Preview(Contract):
    csv_text: str = Field(min_length=1, max_length=200_000)


class Commit(Preview):
    request: Identifier


def parse(text):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    rows = []
    try:
        if reader.fieldnames != COLUMNS:
            fail("CSV headers must match the downloadable template exactly.")
        for n, row in enumerate(reader, start=2):
            if n > 201:
                fail("Import at most 200 products at a time.")
            if None in row or any(v is None for v in row.values()):
                fail(f"CSV row {n}: incorrect column count.")
            row = {k: v.strip() for k, v in row.items()}
            try:
                # User-facing CSV money is major currency, never binary float.
                def money(key):
                    v = Decimal(row[key] or "0")
                    if (
                        not v.is_finite()
                        or v < 0
                        or v > 1_000_000_000
                        or v * 100 != (v * 100).to_integral_value()
                    ):
                        raise ValueError("Money requires at most two decimal places.")
                    return int(v * 100)

                payload = ProductCreate(
                    sku=row["sku"],
                    name=row["name"],
                    barcode=row["barcode"],
                    price=money("price"),
                    cost=money("cost"),
                    initial=row["initial"] or "0",
                    reorder=row["reorder"] or "0",
                )
            except (ValueError, InvalidOperation, ValidationError):
                fail(f"CSV row {n}: invalid product fields, money, or quantity.")
            rows.append((n, row, payload.model_dump()))
    except csv.Error:
        fail("Invalid CSV quoting or structure.")
    if not rows:
        fail("CSV contains no product rows.")
    return rows


async def apply(c, u, t, rows):
    ids = []
    for n, row, payload in rows:
        try:
            for field, kind in [("category_code", "category"), ("unit_code", "unit")]:
                identifier = await c.fetchval(
                    "SELECT id FROM lookups WHERE tenant=$1 AND kind=$2 AND code=$3 AND active=true",
                    t,
                    kind,
                    row[field],
                )
                if not identifier:
                    fail(f"Unknown active {kind} code.")
                payload[kind + "_id"] = identifier
            r = await save_product(c, u, {**payload, "action": "product", "tenant": t})
            ids.append(r["id"])
        except HTTPException as e:
            fail(f"CSV row {n}: {e.detail}", e.status_code)
    return ids


@router.post("/preview")
async def preview(tenant: str, payload: Preview, request: Request, user: User):
    security.csrf(request)
    rows = parse(payload.csv_text)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "product", lock=True)
            # Explicit nested rollback leaves no product, movement or audit side effects.
            tx = c.transaction()
            await tx.start()
            try:
                await apply(c, user, tenant, rows)
            finally:
                await tx.rollback()
    return {
        "count": len(rows),
        "items": [
            {
                "row": n,
                "sku": p["sku"].upper(),
                "name": p["name"],
                "price": p["price"],
                "initial": p["initial"],
            }
            for n, _, p in rows
        ],
    }


@router.post("", status_code=201)
async def commit(tenant: str, payload: Commit, request: Request, user: User):
    security.csrf(request)
    rows = parse(payload.csv_text)
    signature = hashlib.sha256(payload.csv_text.encode()).hexdigest()
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "product", lock=True)
            previous = await c.fetchrow(
                "SELECT * FROM catalog_imports WHERE tenant=$1 AND request=$2",
                tenant,
                payload.request,
            )
            if previous:
                if previous["signature"] != signature:
                    fail("Import request identifier already used.", 409)
                return {
                    "id": previous["id"],
                    "product_ids": json.loads(previous["product_ids"]),
                }
            ids = await apply(c, user, tenant, rows)
            identifier = service.uid()
            await c.execute(
                "INSERT INTO catalog_imports(id,tenant,request,signature,product_ids,actor) VALUES($1,$2,$3,$4,$5,$6)",
                identifier,
                tenant,
                payload.request,
                signature,
                json.dumps(ids),
                user["email"],
            )
            await service.audit(
                c,
                tenant,
                user,
                "Catalog imported",
                {"id": identifier, "count": len(ids)},
            )
    return {"id": identifier, "product_ids": ids}


class ExcelUpload(Contract):
    file_base64: str = Field(min_length=1, max_length=1_333_336)


@router.post("/convert-xlsx")
async def convert_excel(
    tenant: str, payload: ExcelUpload, request: Request, user: User
):
    import asyncio
    from ..features.xlsx_import import convert

    security.csrf(request)
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "product")
    return await asyncio.to_thread(convert, payload.file_base64)


@router.get("/template.xlsx")
async def excel_template(tenant: str, user: User):
    from pathlib import Path
    from fastapi.responses import FileResponse

    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "product")
    return FileResponse(
        Path(__file__).resolve().parents[1] / "templates" / "catalog-template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="catalog-template.xlsx",
    )
