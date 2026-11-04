"""Structural regression tests for commerce boundaries (no DB required)."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def test_public_orders_are_request_only_and_pos_linked():
    text=(ROOT/'app/api/storefront.py').read_text()
    assert "status='fulfilled'" in text
    assert "WHERE tenant=$1 AND sale=$2" in text
    assert "same products and quantities" in text
    assert "pickup_request_no_online_payment" in text
    assert "COALESCE(l.featured,false)" in text


def test_migration_is_atomic_and_idempotent():
    text=(ROOT/'app/api/migration_wizard.py').read_text()
    assert 'async with c.transaction()' in text
    assert 'migration_batches' in text
    assert 'SELECT 1 FROM products WHERE tenant=$1 AND sku=$2' in text
    assert "Choose a store or warehouse" in text


def test_seed_public_demo_catalog_is_opt_in():
    text=(ROOT/'demo_seed.py').read_text()
    assert "APP_ENV=production" in text
    assert 'stockdesk-demo-market' in text
    assert 'seed_commerce(conn)' in text
