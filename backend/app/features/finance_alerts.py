"""Read-only financial conditions. Evidence amounts are integer minor units."""
from datetime import timedelta
from ..rules import business_date, grants

KIND_PERMISSIONS = {
    'low_stock': 'alerts', 'stock_out': 'alerts', 'expiry': 'alerts',
    'customer_overdue': 'credit', 'supplier_overdue': 'finance', 'cash_variance': 'finance',
}
FINANCE_KINDS = frozenset(('customer_overdue', 'supplier_overdue', 'cash_variance'))


def allowed_kinds(role):
    return [kind for kind, permission in KIND_PERMISSIONS.items() if permission in grants(role)]


async def matches(c, tenant, rule, now):
    minimum = int(rule['minimum_amount'] * 100)
    cutoff = business_date() - timedelta(days=rule['overdue_days'])
    if rule['kind'] == 'customer_overdue':
        return await c.fetch('''SELECT r.id AS entity,r.sale AS reference,c.name,r.due_date,
            x.amount,t.currency FROM receivables r
            JOIN customers c ON c.tenant=r.tenant AND c.id=r.customer JOIN tenants t ON t.id=r.tenant
            JOIN LATERAL (SELECT COALESCE(SUM(l.amount),0)::bigint AS amount FROM customer_ledger l
                WHERE l.tenant=r.tenant AND l.receivable=r.id) x ON true
            WHERE r.tenant=$1 AND r.status='open' AND r.due_date<$2 AND x.amount>0 AND x.amount>=$3
            ORDER BY r.id LIMIT 5001''', tenant, cutoff, minimum)
    if rule['kind'] == 'supplier_overdue':
        return await c.fetch('''SELECT b.id AS entity,b.invoice_number AS reference,s.name,b.due_date,
            v.balance::bigint AS amount,t.currency FROM supplier_bills b
            JOIN supplier_bill_balances v ON v.tenant=b.tenant AND v.id=b.id
            JOIN suppliers s ON s.tenant=b.tenant AND s.id=b.supplier JOIN tenants t ON t.id=b.tenant
            WHERE b.tenant=$1 AND b.status='posted' AND b.due_date<$2 AND v.balance>0 AND v.balance>=$3
            ORDER BY b.id LIMIT 5001''', tenant, cutoff, minimum)
    return await c.fetch('''SELECT s.id AS entity,s.id AS reference,u.name,s.closed,
        s.variance AS amount,s.expected_cash,s.counted_cash,t.currency
        FROM till_sessions s JOIN users u ON u.id=s.actor JOIN tenants t ON t.id=s.tenant
        WHERE s.tenant=$1 AND s.status='closed' AND s.closed>=$2 AND s.closed<=$4
        AND s.variance<>0 AND abs(s.variance)>=$3 ORDER BY s.id LIMIT 5001''',
        tenant, now-timedelta(days=rule['lookback_days']), minimum, now)
