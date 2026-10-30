from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from .router import User, authenticated
from .. import db, service
from ..rules import business_date, fail
from ..features.reporting import analyze

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}",
    dependencies=[Depends(authenticated)],
    tags=["Management reports"],
)


@router.get("/management-report")
async def report(
    tenant: str, user: User, days: int = Query(30, ge=1, le=90), end: date | None = None
):
    end = end or business_date() - timedelta(days=1)
    if end < date(2000, 1, 1):
        fail("Report end must be on or after 2000-01-01.")
    if end >= business_date():
        fail("Report end must be a completed business day.")
    start = end - timedelta(days=days - 1)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            return await load_management_report(c, tenant, user, days, end)


async def load_management_report(c, tenant, user, days, end):
    """Read using the caller's transaction (also used by scheduled snapshots)."""
    start = end - timedelta(days=days - 1)
    business, _ = await service.authorize(c, user, tenant, "cost")
    sales = await c.fetch(
        "SELECT id,actor,discount,tax,tax_included,tax_snapshot,(created AT TIME ZONE 'Asia/Karachi')::date AS day,extract(hour FROM created AT TIME ZONE 'Asia/Karachi')::int AS hour FROM sales WHERE tenant=$1 AND status='completed' AND (created AT TIME ZONE 'Asia/Karachi')::date BETWEEN $2 AND $3 ORDER BY created,id LIMIT 10001",
        tenant,
        start,
        end,
    )
    if len(sales) > 10000:
        fail("Report exceeds 10000 invoices. Choose a shorter period.", 422)
    items = await c.fetch(
        "SELECT i.* FROM sale_items i JOIN sales s ON s.tenant=i.tenant AND s.id=i.sale WHERE i.tenant=$1 AND s.status='completed' AND (s.created AT TIME ZONE 'Asia/Karachi')::date BETWEEN $2 AND $3 ORDER BY i.sale,i.sku LIMIT 50001",
        tenant,
        start,
        end,
    )
    if len(items) > 50000:
        fail("Report exceeds 50000 sale lines. Choose a shorter period.", 422)
    products = await c.fetch(
        "SELECT id,sku,name,category,created FROM products WHERE tenant=$1",
        tenant,
    )

    return {
        **analyze(sales, items, products, days, end),
        "business": business["name"],
        "currency": business["currency"],
    }


@router.get("/operational-report")
async def operational_report(
    tenant: str,
    user: User,
    days: int = Query(30, ge=1, le=90),
    minimum_baskets: int = Query(2, ge=2, le=10000),
    horizon_days: int = Query(30, ge=1, le=365),
    demand_pct: int = Query(0, ge=-100, le=500),
    price_pct: int = Query(0, ge=-100, le=500),
    cost_pct: int = Query(0, ge=-100, le=500),
):
    from ..features.operational_reports import (
        tax_register,
        stock_age,
        basket_analysis,
        scenario,
    )

    end = business_date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            business, _ = await service.authorize(c, user, tenant, "cost")
            sales = await c.fetch(
                "SELECT *, (created AT TIME ZONE 'Asia/Karachi')::date AS day FROM sales WHERE tenant=$1 AND status='completed' AND (created AT TIME ZONE 'Asia/Karachi')::date BETWEEN $2 AND $3 ORDER BY created,id LIMIT 10001",
                tenant,
                start,
                end,
            )
            if len(sales) > 10000:
                fail("Report exceeds 10000 invoices. Choose a shorter period.", 422)
            items = await c.fetch(
                "SELECT i.* FROM sale_items i JOIN sales s ON s.tenant=i.tenant AND s.id=i.sale WHERE i.tenant=$1 AND s.status='completed' AND (s.created AT TIME ZONE 'Asia/Karachi')::date BETWEEN $2 AND $3 ORDER BY i.sale,i.sku LIMIT 50001",
                tenant,
                start,
                end,
            )
            if len(items) > 50000:
                fail("Report exceeds 50000 sale lines. Choose a shorter period.", 422)
            products = await c.fetch(
                "SELECT id,sku,name FROM products WHERE tenant=$1", tenant
            )
            batches = await c.fetch(
                "SELECT b.*,p.sku,p.name,p.cost,l.name AS unit_name FROM stock_batches b JOIN products p ON p.tenant=b.tenant AND p.id=b.product JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id WHERE b.tenant=$1 AND b.stock>0 ORDER BY b.created,b.id LIMIT 10001",
                tenant,
            )
            if len(batches) > 10000:
                fail("Stock report exceeds 10000 batches.", 422)
    tax = tax_register(sales)
    from ..rules import line_amount

    net = tax["summary"]["taxable"]
    cost = sum(line_amount(i["cost"], i["quantity"]) for i in items)
    return dict(
        start=start,
        end=end,
        timezone="Asia/Karachi",
        business=business["name"],
        currency=business["currency"],
        minimum_baskets=minimum_baskets,
        demand_pct=demand_pct,
        price_pct=price_pct,
        cost_pct=cost_pct,
        tax=tax,
        stock=stock_age(batches, business_date()),
        baskets=basket_analysis(sales, items, products, minimum_baskets),
        scenario=scenario(
            dict(net_sales=net, cost=cost),
            days,
            horizon_days,
            demand_pct,
            price_pct,
            cost_pct,
        ),
    )


@router.get("/inventory-turnover")
async def inventory_turnover(
    tenant: str, user: User, days: int = Query(30, ge=1, le=90)
):
    from ..features.turnover import metrics

    end = business_date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            business, _ = await service.authorize(c, user, tenant, "cost")
            rows = await c.fetch(
                """WITH daily AS (
                SELECT product,(created AT TIME ZONE 'Asia/Karachi')::date AS day,
                SUM(quantity) AS delta,
                -COALESCE(SUM(quantity) FILTER(WHERE type='SALE'),0) AS sold,
                COALESCE(SUM(quantity) FILTER(WHERE type='RETURN'),0) AS returned
                FROM movements WHERE tenant=$1 AND created < (($3::date+1)::timestamp AT TIME ZONE 'Asia/Karachi')
                GROUP BY product,(created AT TIME ZONE 'Asia/Karachi')::date
            ), stats AS (
                SELECT product,
                COALESCE(SUM(delta) FILTER(WHERE day<$2),0) AS opening,
                SUM(delta) AS closing,
                SUM(delta*CASE WHEN day<$2 THEN $4 ELSE ($3-day+1) END) AS stock_days,
                COALESCE(SUM(sold) FILTER(WHERE day>=$2),0) AS sold,
                COALESCE(SUM(returned) FILTER(WHERE day>=$2),0) AS returned
                FROM daily GROUP BY product
            ) SELECT p.id,p.sku,p.name,l.name AS unit,
              COALESCE(s.opening,0) AS opening,COALESCE(s.closing,0) AS closing,
              COALESCE(s.stock_days,0) AS stock_days,COALESCE(s.sold,0) AS sold,COALESCE(s.returned,0) AS returned
              FROM products p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id
              LEFT JOIN stats s ON s.product=p.id
              WHERE p.tenant=$1 AND p.created < (($3::date+1)::timestamp AT TIME ZONE 'Asia/Karachi')
              ORDER BY p.sku,p.id LIMIT 10001""",
                tenant,
                start,
                end,
                days,
            )
            if len(rows) > 10000:
                fail("Turnover report exceeds 10000 products.", 422)
    return dict(
        start=start,
        end=end,
        days=days,
        timezone="Asia/Karachi",
        business=business["name"],
        currency=business["currency"],
        items=metrics(rows, days),
    )


from typing import Literal


@router.get("/report-export/{name}.{format}")
async def report_export(
    tenant: str,
    user: User,
    name: Literal[
        "products",
        "categories",
        "cashiers",
        "hours",
        "tax-summary",
        "tax-invoices",
        "stock-age",
        "basket-analysis",
        "what-if",
        "turnover",
    ],
    format: Literal["xlsx", "pdf"],
    days: int = Query(30, ge=1, le=90),
    minimum_baskets: int = Query(2, ge=2, le=10000),
    horizon_days: int = Query(30, ge=1, le=365),
    demand_pct: int = Query(0, ge=-100, le=500),
    price_pct: int = Query(0, ge=-100, le=500),
    cost_pct: int = Query(0, ge=-100, le=500),
):
    import asyncio
    from fastapi.responses import Response
    from ..features.report_exports import xlsx_export, pdf_export

    if name == "turnover":
        data = await inventory_turnover(tenant, user, days)
    elif name in ("products", "categories", "cashiers", "hours"):
        data = await report(tenant, user, days)
    else:
        data = await operational_report(
            tenant,
            user,
            days,
            minimum_baskets,
            horizon_days,
            demand_pct,
            price_pct,
            cost_pct,
        )
    content = await asyncio.to_thread(
        xlsx_export if format == "xlsx" else pdf_export, name, data
    )
    mime = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if format == "xlsx"
        else "application/pdf"
    )
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{name}.{format}"',
            "Cache-Control": "no-store",
        },
    )
