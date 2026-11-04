"""Tenant-owned public product catalog and staff-managed pickup order requests.

A public request does not charge a card, reserve stock, or generate an invoice.
Staff fulfilment requires a real completed POS sale attached to the request.
"""
import hashlib
import json
import re
import io
import base64
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, Query, Request, Response
from PIL import Image, UnidentifiedImageError
from pydantic import Field, model_validator
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail

public_router = APIRouter(prefix="/api/storefronts", tags=["Public storefront"])
router = APIRouter(prefix="/api/v1/tenants/{tenant}/storefront", tags=["Storefront management"], dependencies=[Depends(authenticated)])


class Settings(Contract):
    slug: str = Field(min_length=3, max_length=48, pattern=r"^[a-z0-9][a-z0-9-]{2,47}$")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    published: bool = False


class ProductPhoto(Contract):
    image_base64: str = Field(min_length=128, max_length=2_800_000)


def optimized_photo(encoded: str) -> tuple[bytes, int, int]:
    """Decode an image without trusting its extension; strip EXIF and cap size."""
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 2_000_000:
            fail("Product photo must be 2 MB or smaller.", 413)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                fail("Only JPEG, PNG and WebP product photos are accepted.", 415)
            if image.width * image.height > 12_000_000:
                fail("Product photo dimensions exceed the safe limit.", 413)
            image.load()
            # Composite transparency against white, rather than producing black
            # product-photo backgrounds for transparent PNG/WebP assets.
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            background.alpha_composite(rgba)
            rgb = background.convert("RGB")
            rgb.thumbnail((960, 960))
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=80, optimize=True)
            content = output.getvalue()
            if len(content) > 600_000:
                fail("Optimized photo is too large. Use a smaller image.", 413)
            return content, rgb.width, rgb.height
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        fail("Invalid or damaged product photo.", 422)


class Listing(Contract):
    published: bool
    featured: bool = False
    sort_order: int = Field(default=0, ge=0, le=10000)


class OrderLine(Contract):
    product: Identifier
    quantity: Decimal = Field(gt=0, le=1000, decimal_places=3)


class Order(Contract):
    request_id: str = Field(min_length=16, max_length=100)
    customer_name: str = Field(min_length=2, max_length=150)
    customer_phone: str = Field(min_length=6, max_length=30)
    customer_email: str = Field(default="", max_length=254)
    notes: str = Field(default="", max_length=500)
    items: list[OrderLine] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def no_duplicates(self):
        if len({item.product for item in self.items}) != len(self.items):
            raise ValueError("Each product can appear only once in an order.")
        if self.customer_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.customer_email):
            raise ValueError("Enter a valid email address or leave it blank.")
        return self


class Fulfil(Contract):
    sale_id: Identifier


@router.get("")
async def settings(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "product")
        cfg = await c.fetchrow("SELECT slug,title,description,published FROM storefronts WHERE tenant=$1", tenant)
        products = await c.fetch("""SELECT p.id,p.sku,p.name,p.stock,p.price,
           COALESCE(l.published,false) AS published,COALESCE(l.featured,false) AS featured,
           COALESCE(l.sort_order,0) AS sort_order,
           (m.product IS NOT NULL) AS has_image, m.updated AS image_updated
           FROM products p LEFT JOIN storefront_listings l ON l.tenant=p.tenant AND l.product=p.id
           LEFT JOIN storefront_product_media m ON m.tenant=p.tenant AND m.product=p.id
           WHERE p.tenant=$1 AND p.active ORDER BY p.name LIMIT 500""", tenant)
        return {"settings": dict(cfg) if cfg else None, "products": service.rows(products)}


@router.put("")
async def configure(tenant: str, payload: Settings, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "product", lock=True)
            await c.execute("""INSERT INTO storefronts(tenant,slug,title,description,published)
               VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant) DO UPDATE SET
               slug=EXCLUDED.slug,title=EXCLUDED.title,description=EXCLUDED.description,
               published=EXCLUDED.published,updated=now()""",
                tenant, payload.slug, payload.title, payload.description, payload.published)
            await service.audit(c, tenant, user, "Storefront settings updated", {"slug": payload.slug, "published": payload.published})
    return {"ok": True, "url": f"/shop/{payload.slug}"}


@router.put("/products/{product_id}")
async def list_product(tenant: str, product_id: str, payload: Listing, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "product", lock=True)
            if not await c.fetchval("SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND active", tenant, product_id):
                fail("Active product not found.", 404)
            await c.execute("""INSERT INTO storefront_listings(tenant,product,published,featured,sort_order)
               VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant,product) DO UPDATE
               SET published=EXCLUDED.published,featured=EXCLUDED.featured,sort_order=EXCLUDED.sort_order""",
                tenant, product_id, payload.published, payload.featured, payload.sort_order)
            await service.audit(c, tenant, user, "Storefront listing changed", {"product": product_id, "published": payload.published})
    return {"ok": True}


@router.put("/products/{product_id}/image")
async def save_product_image(tenant: str, product_id: str, payload: ProductPhoto, request: Request, user: User):
    security.csrf(request)
    # Decode outside the DB transaction, preserving storage and CPU limits.
    content, width, height = optimized_photo(payload.image_base64)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "product", lock=True)
            if not await c.fetchval("SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND active", tenant, product_id):
                fail("Active product not found.", 404)
            await c.execute("""INSERT INTO storefront_product_media(tenant,product,image,mime,width,height)
              VALUES($1,$2,$3,'image/jpeg',$4,$5)
              ON CONFLICT(tenant,product) DO UPDATE SET image=EXCLUDED.image,
              width=EXCLUDED.width,height=EXCLUDED.height,updated=now()""",
              tenant, product_id, content, width, height)
            await service.audit(c,tenant,user,"Storefront product photo saved",{"product":product_id})
    return {"ok": True, "width": width, "height": height}


@router.get("/products/{product_id}/image", response_class=Response)
async def staff_product_image(tenant: str, product_id: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,"product")
        image = await c.fetchval("SELECT image FROM storefront_product_media WHERE tenant=$1 AND product=$2", tenant, product_id)
    if image is None:
        fail("Product image not found.", 404)
    return Response(bytes(image),media_type="image/jpeg",
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@router.delete("/products/{product_id}/image")
async def remove_product_image(tenant: str, product_id: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"product",lock=True)
            await c.execute("DELETE FROM storefront_product_media WHERE tenant=$1 AND product=$2",tenant,product_id)
            await service.audit(c,tenant,user,"Storefront product photo removed",{"product":product_id})
    return {"ok": True}


@public_router.get("/{slug}/products/{product_id}/image", response_class=Response)
async def public_product_image(slug: str, product_id: str):
    async with db.pool.acquire() as c:
        image = await c.fetchval("""SELECT m.image FROM storefront_product_media m
            JOIN storefronts s ON s.tenant=m.tenant AND s.slug=$1 AND s.published
            JOIN tenants t ON t.id=m.tenant AND t.status='active'
            JOIN storefront_listings l ON l.tenant=m.tenant AND l.product=m.product AND l.published
            JOIN products p ON p.tenant=m.tenant AND p.id=m.product AND p.active AND p.stock>0
            WHERE m.product=$2""", slug, product_id)
    if image is None:
        fail("Product image not available.", 404)
    return Response(bytes(image), media_type="image/jpeg",
                    headers={"Cache-Control":"public, max-age=300", "X-Content-Type-Options":"nosniff"})


@public_router.get("/{slug}")
async def catalog(slug: str, q: str = Query(default="", max_length=80)):
    async with db.pool.acquire() as c:
        cfg = await c.fetchrow("""SELECT s.tenant,s.slug,s.title,s.description,t.currency
            FROM storefronts s JOIN tenants t ON t.id=s.tenant
            WHERE s.slug=$1 AND s.published AND t.status='active'""", slug)
        if not cfg:
            fail("Storefront is not available.", 404)
        products = await c.fetch("""SELECT p.id,p.sku,p.name,p.price,p.stock,p.barcode,
          COALESCE(l.featured,false) AS featured,
          EXISTS(SELECT 1 FROM storefront_product_media m WHERE m.tenant=p.tenant AND m.product=p.id) AS has_image,
          (SELECT m.updated FROM storefront_product_media m WHERE m.tenant=p.tenant AND m.product=p.id) AS image_updated
          FROM storefront_listings l JOIN products p ON p.tenant=l.tenant AND p.id=l.product
          WHERE l.tenant=$1 AND l.published AND p.active AND p.stock>0
          AND ($2='' OR strpos(lower(p.name||' '||p.sku),lower($2))>0)
          ORDER BY l.featured DESC,l.sort_order,p.name LIMIT 100""",cfg['tenant'],q)
        return {"store": {k: cfg[k] for k in ("slug","title","description","currency")},
                "items": service.rows(products), "order_mode": "pickup_request_no_online_payment"}


def fingerprint(data: Order) -> str:
    return hashlib.sha256(json.dumps(data.model_dump(mode="json",exclude={"request_id"}),sort_keys=True,separators=(",", ":")).encode()).hexdigest()


def line_total(price: int, quantity: Decimal) -> int:
    return int((Decimal(price) * quantity).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@public_router.post("/{slug}/orders", status_code=201)
async def place_order(slug: str, payload: Order, request: Request):
    if len((await request.body())) > 12000:
        fail("Order request is too large.", 413)
    signature = fingerprint(payload)
    # Address is used only to restrict request volume, never shown in public responses.
    # Nginx overwrites X-Real-IP, so browser-supplied values are not trusted downstream.
    ip = request.headers.get('x-real-ip') or (request.client.host if request.client else 'unknown')
    if not re.fullmatch(r'[0-9a-fA-F.:]{3,45}', ip):
        ip = 'unknown' 
    ip_digest = hashlib.sha256(ip.encode()).hexdigest()
    async with db.pool.acquire() as c:
        async with c.transaction():
            cfg = await c.fetchrow("""SELECT s.tenant,t.currency FROM storefronts s
                JOIN tenants t ON t.id=s.tenant WHERE s.slug=$1 AND s.published
                AND t.status='active' FOR SHARE OF t""", slug)
            if not cfg:
                fail("Storefront is not available.", 404)
            tenant = cfg["tenant"]
            # Serialize public orders for this tenant to bound request rate and preserve idempotency.
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "storefront:" + tenant + ":" + ip_digest)
            previous = await c.fetchrow("SELECT id,signature,status FROM storefront_orders WHERE tenant=$1 AND request_id=$2",tenant,payload.request_id)
            if previous:
                if previous['signature'] != signature:
                    fail("Request ID was already used for different contents.", 409)
                return {"id":previous['id'], "status":previous['status'],"duplicate":True}
            recent = await c.fetchval("""SELECT count(*) FROM storefront_orders
                WHERE tenant=$1 AND ip_digest=$2 AND created>now()-interval '1 hour'""",tenant,ip_digest)
            if recent >= 12:
                fail("Too many orders from this connection. Try again later.", 429)
            ids = [item.product for item in payload.items]
            rows = await c.fetch("""SELECT p.id,p.name,p.price,p.stock FROM products p
                JOIN storefront_listings l ON l.tenant=p.tenant AND l.product=p.id
                WHERE p.tenant=$1 AND p.id=ANY($2::text[]) AND p.active AND l.published AND p.stock>0
                ORDER BY p.id""", tenant,ids)
            found={r['id']: r for r in rows}
            if len(rows) != len(ids):
                fail("Some products are no longer available. Refresh your cart.", 409)
            total=0
            for line in payload.items:
                row=found[line.product]
                if line.quantity > row['stock']:
                    fail(f"Not enough stock for {row['name']}.",409)
                total += line_total(row['price'],line.quantity)
            if total > 100_000_000_000:
                fail("Order exceeds the permitted value.")
            oid=service.uid()
            await c.execute("""INSERT INTO storefront_orders(id,tenant,request_id,signature,customer_name,customer_phone,customer_email,notes,total,currency,ip_digest)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                oid,tenant,payload.request_id,signature,payload.customer_name,payload.customer_phone,payload.customer_email,payload.notes,total,cfg['currency'],ip_digest)
            for line in payload.items:
                row=found[line.product]
                await c.execute("""INSERT INTO storefront_order_lines(tenant,order_id,product,quantity,unit_price,name)
                   VALUES($1,$2,$3,$4,$5,$6)""",tenant,oid,line.product,line.quantity,row['price'],row['name'])
    return {"id":oid,"status":"pending","total":total,"currency":cfg['currency'],
            "message":"Order request received. The store will confirm availability and payment at pickup."}


@router.get("/orders")
async def orders(tenant: str, user: User, status: str = Query(default="pending",pattern=r"^(pending|accepted|rejected|fulfilled|all)$")):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,"sale")
        rows=await c.fetch("""SELECT id,customer_name,customer_phone,customer_email,notes,total,currency,
          status,sale_id,created FROM storefront_orders
          WHERE tenant=$1 AND ($2='all' OR status=$2) ORDER BY created DESC LIMIT 100""",tenant,status)
        result=service.rows(rows)
        for order in result:
            order['items']=service.rows(await c.fetch("SELECT product,name,quantity,unit_price FROM storefront_order_lines WHERE tenant=$1 AND order_id=$2 ORDER BY name",tenant,order['id']))
        return {"items":result}


@router.post("/orders/{order_id}/accept")
async def accept(tenant: str, order_id: str, request: Request, user: User):
    return await decision(tenant,order_id,"accepted",request,user)


@router.post("/orders/{order_id}/reject")
async def reject(tenant: str, order_id: str, request: Request, user: User):
    return await decision(tenant,order_id,"rejected",request,user)


async def decision(tenant,order_id,status,request,user):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"sale",lock=True)
            updated=await c.fetchrow("""UPDATE storefront_orders SET status=$1,handled_by=$2,updated=now()
              WHERE tenant=$3 AND id=$4 AND status='pending' RETURNING id""",status,user['id'],tenant,order_id)
            if not updated:
                fail("Order must be pending before changing its status.",409)
            await service.audit(c,tenant,user,"Storefront order " + status,{"order":order_id})
    return {"id":order_id,"status":status}


@router.post("/orders/{order_id}/fulfil")
async def fulfil(tenant: str,order_id: str,payload: Fulfil, request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"sale",lock=True)
            sale=await c.fetchrow("SELECT id,status FROM sales WHERE tenant=$1 AND id=$2",tenant,payload.sale_id)
            if not sale or sale['status']!='completed':
                fail("A completed POS sale is required to fulfil this order.",409)
            requested=await c.fetch('SELECT product,quantity FROM storefront_order_lines WHERE tenant=$1 AND order_id=$2',tenant,order_id)
            sold=await c.fetch('SELECT product,quantity FROM sale_items WHERE tenant=$1 AND sale=$2',tenant,payload.sale_id)
            expected={r['product']:r['quantity'] for r in requested}
            actual={r['product']:r['quantity'] for r in sold}
            if not expected or expected!=actual:
                fail('The POS invoice must contain the same products and quantities as the order.',409)
            # Do not let the same sale close unrelated orders.
            if await c.fetchval("SELECT 1 FROM storefront_orders WHERE tenant=$1 AND sale_id=$2",tenant,payload.sale_id):
                fail("This POS sale already belongs to another online order.",409)
            order=await c.fetchrow("""UPDATE storefront_orders SET status='fulfilled',sale_id=$1,handled_by=$2,updated=now()
              WHERE tenant=$3 AND id=$4 AND status='accepted' RETURNING id""",
              payload.sale_id,user['id'],tenant,order_id)
            if not order:
                fail("Accept the order before fulfilling it.",409)
            await service.audit(c,tenant,user,"Storefront order fulfilled",{"order":order_id,"sale":payload.sale_id})
    return {"id":order_id,"status":"fulfilled","sale_id":payload.sale_id}
