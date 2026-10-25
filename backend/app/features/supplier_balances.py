"""Balances derived from immutable credits and non-void payment/refund records."""


async def totals(c, tenant, bill):
    r = await c.fetchrow(
        """SELECT
    COALESCE((SELECT SUM(total) FROM supplier_returns WHERE tenant=$1 AND bill=$2),0) AS credited,
    COALESCE((SELECT SUM(amount) FROM supplier_refunds WHERE tenant=$1 AND bill=$2 AND status='posted'),0) AS refunded""",
        tenant,
        bill,
    )
    return dict(r)
