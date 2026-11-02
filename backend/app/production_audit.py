"""Read-only release readiness audit. Run: python -m app.production_audit.

Exits non-zero on inconsistencies; does not mutate business data. Use a DB user
with read permissions and a configured DATABASE_URL. Does not prove fiscal compliance.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import asyncpg
from .production import production_errors
from .config import DATABASE_URL


async def audit():
    report = {'status': 'pass', 'checks': [], 'warnings': []}

    def check(name, passed, details):
        report['checks'].append({'check': name, 'passed': bool(passed), 'details': details})
        if not passed:
            report['status'] = 'fail'

    for error in production_errors():
        check('production_configuration', False, error)
    if not production_errors():
        check('production_configuration', True, 'Environment policy checks passed (or APP_ENV is not production).')
    connection = await asyncpg.connect(DATABASE_URL, timeout=10, command_timeout=30)
    try:
        async with connection.transaction(readonly=True):
            migrations_dir = Path(__file__).resolve().parents[1] / 'migrations'
            expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in migrations_dir.glob('*.sql')}
            applied_rows = await connection.fetch('SELECT name,checksum FROM schema_migrations')
            applied = {r['name']:r['checksum'] for r in applied_rows}
            missing = sorted(set(expected) - set(applied))
            changed = sorted(k for k in expected.keys() & applied.keys() if expected[k] != applied[k])
            unknown = sorted(set(applied) - set(expected))
            check('migration_integrity', not (missing or changed or unknown),
                  {'applied': len(applied), 'missing': missing, 'modified': changed, 'unrecognized': unknown})

            # No business data is changed. Read reconciliation per product and tenant.
            row = await connection.fetchrow('''
                WITH global_stock AS (
                  SELECT p.tenant,p.id AS product, COALESCE(SUM(m.quantity),0) AS quantity
                  FROM products p LEFT JOIN movements m ON m.tenant=p.tenant AND m.product=p.id
                  GROUP BY p.tenant,p.id
                ), location_stock AS (
                  SELECT tenant,product,SUM(quantity) AS quantity
                  FROM warehouse_balances GROUP BY tenant,product
                )
                SELECT COUNT(*) FILTER(WHERE COALESCE(l.quantity,0)>g.quantity) AS over_allocated,
                       COUNT(*) FILTER(WHERE g.quantity<0) AS negative_global,
                       COUNT(*) FILTER(WHERE l.quantity IS NOT NULL AND l.quantity<>g.quantity) AS not_reconciled,
                       COUNT(*) AS products
                FROM global_stock g LEFT JOIN location_stock l
                    ON l.tenant=g.tenant AND l.product=g.product
            ''')
            check('inventory_no_overallocation', row['over_allocated']==0 and row['negative_global']==0,
                  {'over_allocated':row['over_allocated'], 'negative_global':row['negative_global'], 'products_checked':row['products']})
            report['warnings'].append(f"{row['not_reconciled']} products with location balances are not fully reconciled to global movements; location-level POS posting remains incomplete.")
            journals = await connection.fetchval('''
                SELECT COUNT(*) FROM (
                  SELECT j.id FROM gl_journals j LEFT JOIN gl_entries e
                    ON e.tenant=j.tenant AND e.journal=j.id
                  GROUP BY j.id HAVING COALESCE(SUM(e.debit),0)<>COALESCE(SUM(e.credit),0)
                     OR COUNT(e.journal)<2
                ) bad
            ''')
            check('general_ledger_balanced', journals==0, {'imbalanced_or_empty_journals':journals})
            sale_gap=await connection.fetchval("""SELECT count(*) FROM sales s WHERE s.status='completed' AND NOT EXISTS
                (SELECT 1 FROM gl_journals j WHERE j.tenant=s.tenant AND j.request='sale:'||s.id)""")
            receipt_gap=await connection.fetchval("""SELECT count(*) FROM purchase_receipts r WHERE NOT EXISTS
                (SELECT 1 FROM gl_journals j WHERE j.tenant=r.tenant AND j.request='receipt:'||r.id)""")
            report['warnings'].append(f'{sale_gap} completed historical sales and {receipt_gap} historical receipts lack automated GL entries. Accountant-approved backfill is required.')
            conflicts=await connection.fetchval("SELECT count(*) FROM offline_operations WHERE status='rejected'")
            report['warnings'].append(f'{conflicts} offline replay conflicts require terminal-level resolution.')
            pending_fbr=await connection.fetchval("SELECT count(*) FROM fbr_sandbox_validations WHERE status IN ('pending','uncertain')")
            report['warnings'].append(f'{pending_fbr} FBR sandbox validations are pending or inconclusive; none implies certification.')
            demo_count = await connection.fetchval("SELECT COUNT(*) FROM tenants WHERE name='StockDesk Demo Retail Group'")
            if demo_count:
                report['warnings'].append(f'{demo_count} demonstration tenant(s) found. Remove demo access before exposing production.')
            report['warnings'].extend([
                'External payment settlements and FBR fiscal certification are not verified by this audit.',
                'Backup restoration, concurrency, offline replay, and subscription webhook tests require staging exercises.'
            ])
    finally:
        await connection.close()
    return report


def main():
    try:
        result = asyncio.run(audit())
    except Exception as error:
        result = {'status':'fail', 'checks':[{'check':'audit_execution','passed':False,'details':type(error).__name__ + ': ' + str(error)}]}
    print(json.dumps(result, indent=2, default=str))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
