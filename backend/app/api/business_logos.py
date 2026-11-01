"""Small, immutable business logo assets, persisted in PostgreSQL.

Uploaded files are decoded and re-encoded, never served as arbitrary user bytes.
Historical invoices continue pointing to their original content-hash asset.
"""
import re
from fastapi import APIRouter, Depends, Request, Response
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail
from ..features.tenancy import audit

router = APIRouter(tags=["Business logos"])
MAX_INPUT = 512 * 1024
MAX_PIXELS = 1_440_000


from ..features.brand_images import normalize_logo


@router.post("/api/v1/tenants/{tenant}/business-logo")
async def upload_logo(tenant: str, request: Request, user: User = Depends(authenticated)):
    security.csrf(request)
    if request.headers.get("content-type", "").split(";")[0].strip() not in ("image/png", "image/jpeg"):
        fail("PNG or JPEG content type required.", 415)
    if request.headers.get("content-length") and int(request.headers["content-length"]) > MAX_INPUT:
        fail("Logo exceeds 512 KB.", 413)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_INPUT:
            fail("Logo exceeds 512 KB.", 413)
    digest, data = normalize_logo(bytes(raw))
    url = f"/api/v1/business-logos/{digest}.png"
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "settings", lock=True)
            await c.execute(
                "INSERT INTO business_logo_assets(sha256,media_type,content) VALUES($1,'image/png',$2) ON CONFLICT DO NOTHING",
                digest, data,
            )
            await c.execute("UPDATE tenants SET logo_url=$1 WHERE id=$2", url, tenant)
            await audit(c, tenant, user, "Business logo uploaded", {"sha256": digest})
    return {"logo_url": url}


@router.get("/api/v1/business-logos/{asset}.png")
async def get_logo(asset: str):
    if re.fullmatch(r"[a-f0-9]{64}", asset) is None:
        fail("Logo not found.", 404)
    async with db.pool.acquire() as c:
        data = await c.fetchval("SELECT content FROM business_logo_assets WHERE sha256=$1", asset)
    if data is None:
        fail("Logo not found.", 404)
    return Response(
        bytes(data), media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )
