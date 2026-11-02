"""Fast, database-free checks for sample retail setup."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'demo_seed.py'

def _data(name):
    module = ast.parse(SOURCE.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f'Missing demo data: {name}')

def test_demo_store_and_staff_configuration():
    locations = _data('LOCATIONS')
    staff = _data('STAFF')
    assert len(locations) >= 3
    assert sum(location[2] == 'store' for location in locations) >= 2
    assert {item[2] for item in staff} == {'Owner', 'Manager', 'Cashier', 'Stock Manager'}
    assert len({item[0] for item in locations}) == len(locations)

def test_product_barcodes_unique_and_pricing_valid():
    products = _data('PRODUCTS')
    assert len(products) >= 20
    assert len({p[0] for p in products}) == len(products)
    assert len({p[1] for p in products}) == len(products)
    assert all(p[4] > p[5] >= 0 and p[6] > 0 and p[7] >= 0 for p in products)

def test_demo_location_allocations_cover_sales():
    products = _data('PRODUCTS')
    balances = {(p,store): (info[6]//2 if store == 0 else info[6]//4 if store == 1 else info[6]-info[6]//2-info[6]//4) for p,info in enumerate(products) for store in range(3)}
    for invoice in range(36):
        for offset, item in enumerate(dict.fromkeys([invoice%len(products),(invoice*3+7)%len(products)])):
            quantity = 1 + (invoice+offset)%3
            balances[item, invoice%2] -= quantity
    assert min(balances.values()) >= 0


def test_demo_seed_is_opt_in_and_does_not_print_password():
    source = SOURCE.read_text()
    assert 'DEMO_SEED_CONFIRM' in source
    assert 'DEMO_PASSWORD' in source
    assert 'async with conn.transaction()' in source
    assert 'ON CONFLICT' in source
    assert "print(pwd)" not in source
