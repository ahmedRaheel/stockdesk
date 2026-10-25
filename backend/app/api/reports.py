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
