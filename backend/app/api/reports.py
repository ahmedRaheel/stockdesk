from datetime import timedelta
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
async def report(tenant: str, user: User, days: int = Query(30, ge=1, le=90)):
    end = business_date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "cost")
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
    return analyze(sales, items, products, days, end)


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
            await service.authorize(c, user, tenant, "cost")
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
