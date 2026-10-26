"""FastAPI entry point. No cross-origin API access: deploy behind one web origin."""

import asyncio, json, logging, uuid, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from asyncpg import UniqueViolationError, CheckViolationError, PostgresError
from . import db, config, security, service
from .rules import fail, email, password, clean
from .pdf import invoice_pdf, barcode_pdf

log = logging.getLogger("stockdesk")


@asynccontextmanager
async def lifespan(app):
    await db.connect()
    async with db.pool.acquire() as c:
        # Explicit bootstrap credentials, never a public first-user admin shortcut.
        if not await c.fetchval("SELECT 1 FROM users WHERE is_admin=true"):
            if not config.ADMIN_EMAIL or not config.ADMIN_PASSWORD:
                raise RuntimeError(
                    "Set ADMIN_EMAIL and ADMIN_PASSWORD to bootstrap the platform administrator."
                )
            hashed = await security.hash_password(config.ADMIN_PASSWORD)
            await c.execute(
                "INSERT INTO users(id,email,name,password_hash,is_admin) VALUES($1,$2,$3,$4,true) ON CONFLICT(email) DO NOTHING",
                str(uuid.uuid4()),
                email(config.ADMIN_EMAIL),
                "Platform Administrator",
                hashed,
            )
    from .features.alerts import run_worker
    from contextlib import suppress

    worker = asyncio.create_task(run_worker()) if config.ALERT_WORKER_ENABLED else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await db.close()


app = FastAPI(
    title="StockDesk Inventory & POS",
    version="1.26.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(UniqueViolationError)
async def unique_error(request, exc):
    return JSONResponse(
        {
            "error": "This email, SKU, barcode or submission already exists. Refresh before retrying."
        },
        status_code=409,
    )


@app.exception_handler(CheckViolationError)
async def check_error(request, exc):
    return JSONResponse(
        {
            "error": "The operation would create invalid or negative stock. Refresh and retry."
        },
        status_code=409,
    )


@app.exception_handler(PostgresError)
async def database_error(request, exc):
    log.exception("Database error")
    return JSONResponse(
        {"error": "The database could not complete the operation."}, status_code=500
    )


@app.middleware("http")
async def headers(request, call_next):
    started = time.monotonic()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    r = await call_next(request)
    log.info(
        "http_request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
        request.method,
        request.url.path,
        r.status_code,
        (time.monotonic() - started) * 1000,
        request_id,
    )
    r.headers["X-Request-ID"] = request_id
    r.headers["Cache-Control"] = "no-store"
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    return r


async def body(request):
    security.csrf(request)
    if "application/json" not in request.headers.get("content-type", ""):
        fail("JSON required.", 415)
    raw = await request.body()
    if len(raw) > 100000:
        fail("Request too large.", 413)
    try:
        b = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        fail("Invalid JSON.")
    if not isinstance(b, dict):
        fail("JSON object required.")
    return b


@app.get("/api/health")
async def health():
    async with db.pool.acquire() as c:
        await c.fetchval("SELECT 1")
    return {"status": "ok"}


@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    b = await body(request)
    address = email(b.get("email"))
    pwd = password(b.get("password"))
    async with db.pool.acquire() as c:
        # Nginx rate limiting supplements this per-account limit, with no IP-header trust.
        await security.login_limit(c, "account:" + address)
        u = await c.fetchrow("SELECT * FROM users WHERE email=$1", address)
        valid = await security.verify_password(
            pwd, u["password_hash"] if u else security.DUMMY_HASH
        )
        if not u or not u["active"] or not valid:
            fail("Invalid email or password.", 401)
        await c.execute(
            "DELETE FROM login_limits WHERE key=$1",
            security.digest("account:" + address),
        )
        await c.execute("DELETE FROM sessions WHERE expires<now()")
        await security.session(c, u["id"], response)
        return {"user": service.public_user(u)}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    security.csrf(request)
    async with db.pool.acquire() as c:
        await c.execute(
            "DELETE FROM sessions WHERE token_hash=$1",
            security.digest(security.credential(request)),
        )
    response.delete_cookie("stockdesk_session", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(request: Request):
    async with db.pool.acquire() as c:
        return {"user": service.public_user(await security.identity(c, request))}


@app.post("/api/auth/password")
async def change_password(request: Request, response: Response):
    b = await body(request)
    async with db.pool.acquire() as c:
        u = await security.identity(c, request)
        await security.login_limit(c, "password:" + u["id"])
        if not await security.verify_password(
            password(b.get("current")), u["password_hash"]
        ):
            fail("Current password is incorrect.", 400)
        hashed = await security.hash_password(b.get("password"))
        async with c.transaction():
            await c.execute(
                "UPDATE users SET password_hash=$1 WHERE id=$2", hashed, u["id"]
            )
            await c.execute("DELETE FROM sessions WHERE user_id=$1", u["id"])
            await security.session(c, u["id"], response)
    return {"ok": True}


@app.get("/api/workspace")
async def workspace(request: Request, tenant: str = "", receipt: str = ""):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            u = await security.identity(c, request)
            return jsonable_encoder(
                await service.get_receipt(c, u, tenant, receipt)
                if receipt
                else await service.snapshot(c, u, tenant)
            )


@app.post("/api/workspace")
async def mutate(request: Request):
    b = await body(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            u = await security.identity(c, request)
            return await service.execute(c, u, b)


@app.get("/api/invoices/{sale_id}.pdf")
async def invoice(
    request: Request,
    sale_id: str,
    tenant: str,
    language: str = "en",
    original: bool = False,
):
    if language not in ("en", "ur"):
        fail("Invalid language.")
    async with db.pool.acquire() as c:
        u = await security.identity(c, request)
        data = await service.get_receipt(c, u, tenant, sale_id)
    if original:
        from .api.exchanges import original_receipt

        data = await original_receipt(tenant, sale_id, u)
    pdf = await asyncio.to_thread(
        invoice_pdf, data["sale"], data["items"], language, data.get("tenders")
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{data["sale"]["invoice_number"]}.pdf"'
        },
    )


@app.get("/api/products/{product_id}/barcode.pdf")
async def label(request: Request, product_id: str, tenant: str):
    async with db.pool.acquire() as c:
        u = await security.identity(c, request)
        await service.authorize(c, u, tenant, "product")
        p = await c.fetchrow(
            "SELECT * FROM products WHERE id=$1 AND tenant=$2", product_id, tenant
        )
        if not p:
            fail("Product not found.", 404)
    pdf = await asyncio.to_thread(barcode_pdf, dict(p))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="barcode-label.pdf"'},
    )


@app.get("/api/forecasts")
async def forecasts(
    request: Request,
    tenant: str,
    period: str = "last7",
    lead: int = 7,
    cover: int = 30,
    safety: int = 20,
):
    from .forecast import analyze, window
    from datetime import datetime, timezone

    if not 1 <= lead <= 90 or not 1 <= cover <= 90 or not 0 <= safety <= 100:
        fail("Lead/coverage must be 1–90 days; safety must be 0–100%.")
    try:
        window(period, datetime.now(timezone.utc).date())
    except ValueError:
        fail("Invalid reporting period.")
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            u = await security.identity(c, request)
            await service.authorize(c, u, tenant, "forecast")
            products = service.rows(
                await c.fetch(
                    "SELECT p.*,COALESCE((SELECT SUM(l.quantity-l.received) FROM purchase_lines l JOIN purchase_orders o ON o.tenant=l.tenant AND o.id=l.purchase WHERE l.tenant=p.tenant AND l.product=p.id AND o.status IN ('open','partial')),0) AS incoming,(SELECT MAX(s.created) FROM sale_items i JOIN sales s ON s.id=i.sale AND s.tenant=i.tenant WHERE i.product=p.id AND i.tenant=p.tenant AND s.status='completed') AS last_sale FROM products p WHERE p.tenant=$1 ORDER BY p.name",
                    tenant,
                )
            )
            daily = service.rows(
                await c.fetch(
                    "SELECT i.product,(s.created AT TIME ZONE 'UTC')::date::text AS day,SUM(i.quantity) AS units,SUM(i.line_total)::bigint AS gross FROM sale_items i JOIN sales s ON s.id=i.sale AND s.tenant=i.tenant WHERE s.tenant=$1 AND s.status='completed' AND s.created>=now()-interval '120 days' GROUP BY i.product,2",
                    tenant,
                )
            )
    return await asyncio.to_thread(
        analyze, products, daily, period, lead, cover, safety
    )


from .api.router import router, auth_router

app.include_router(auth_router)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo rejected input: request bodies can include credentials.
    return JSONResponse(
        {
            "error": "Request validation failed.",
            "fields": [
                {"path": ".".join(map(str, e["loc"])), "message": e["msg"]}
                for e in exc.errors()
            ],
        },
        status_code=422,
    )


@app.get("/api/live", tags=["Operations"])
async def live():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    request_id = getattr(request.state, "request_id", "unknown")
    log.exception("Unhandled request error request_id=%s", request_id)
    return JSONResponse(
        {"error": "An unexpected error occurred.", "request_id": request_id},
        status_code=500,
        headers={"X-Request-ID": request_id},
    )


from .api.retail import router as retail_router

app.include_router(retail_router)

from .api.taxes import router as tax_router

app.include_router(tax_router)

from .api.counts import router as count_router

app.include_router(count_router)

from .api.reports import router as reports_router

app.include_router(reports_router)

from .api.payables import router as payables_router

app.include_router(payables_router)

from .api.imports import router as imports_router

app.include_router(imports_router)

from .api.roles import router as roles_router

app.include_router(roles_router)

from .api.audit import router as audit_router

app.include_router(audit_router)

from .api.supplier_returns import router as supplier_returns_router

app.include_router(supplier_returns_router)

from .api.procurement import router as procurement_router

app.include_router(procurement_router)

from .api.promotions import router as promotions_router

app.include_router(promotions_router)

from .api.alerts import router as alerts_router

app.include_router(alerts_router)

from .api.exchanges import router as exchanges_router

app.include_router(exchanges_router)

from .api.feedback import router as feedback_router

app.include_router(feedback_router)

from .api.transaction_approvals import router as transaction_approvals_router

app.include_router(transaction_approvals_router)

from .api.catalog_tools import router as catalog_tools_router

app.include_router(catalog_tools_router)

from .api.cashiers import router as cashiers_router

app.include_router(cashiers_router)

from .api.till_reports import router as till_reports_router

app.include_router(till_reports_router)
