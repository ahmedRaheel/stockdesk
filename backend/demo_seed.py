"""Explicit, idempotent demonstration tenant seeding. Never run on a public production system."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
from app.security import hash_password

NAMESPACE = uuid.UUID('da2a86f1-ec71-4a4e-a858-86e0ca96adf1')
def uid(value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, 'stockdesk-demo-v139:' + value))

TENANT = uid('tenant')
STAFF = [
    ('owner', 'Ayesha Khan', 'Owner'),
    ('manager', 'Bilal Siddiqui', 'Manager'),
    ('cashier', 'Sana Ali', 'Cashier'),
    ('stock', 'Hamza Farooq', 'Stock Manager'),
]
LOCATIONS = [
    ('DHA', 'DHA Flagship', 'store', 'Phase 6, DHA, Karachi'),
    ('GUL', 'Gulshan Express', 'store', 'Gulshan-e-Iqbal, Karachi'),
    ('WH', 'Central Distribution', 'warehouse', 'SITE Industrial Area, Karachi'),
]
# Prices and costs are integer paisa, not rupees.
PRODUCTS = [
    ('GROC-001','8961001000011','Basmati Rice 5kg','Pantry',245000,198000,120,16),
    ('GROC-002','8961001000028','Wheat Flour 10kg','Pantry',185000,149000,100,15),
    ('GROC-003','8961001000035','Cooking Oil 1L','Pantry',59500,47500,180,24),
    ('GROC-004','8961001000042','Sugar 1kg','Pantry',17500,13600,210,30),
    ('GROC-005','8961001000059','Tea 400g','Pantry',92500,76000,95,12),
    ('GROC-006','8961001000066','Salt 800g','Pantry',9000,5800,150,20),
    ('GROC-007','8961001000073','Milk UHT 1L','General',35000,28600,130,15),
    ('GROC-008','8961001000080','Yogurt 500g','General',22000,17500,110,15),
    ('GROC-009','8961001000097','Mineral Water 1.5L','General',12500,8000,260,40),
    ('GROC-010','8961001000103','Orange Juice 1L','General',37000,28500,115,12),
    ('GROC-011','8961001000110','Biscuits Family Pack','General',22000,15200,180,20),
    ('GROC-012','8961001000127','Instant Noodles 4-pack','General',39000,32000,135,20),
    ('GROC-013','8961001000134','Dishwash Liquid 500ml','General',32500,24500,125,18),
    ('GROC-014','8961001000141','Laundry Detergent 1kg','General',72000,59000,100,14),
    ('GROC-015','8961001000158','Tissue Box 200s','General',30000,24500,145,18),
    ('GROC-016','8961001000165','Handwash 250ml','General',34000,27500,100,12),
    ('GROC-017','8961001000172','Toothpaste 150g','General',44000,35000,115,14),
    ('GROC-018','8961001000189','Shampoo 360ml','General',84000,69000,85,12),
    ('GROC-019','8961001000196','Chocolate Bar','General',14000,9900,170,25),
    ('GROC-020','8961001000202','Breakfast Cereal 500g','General',97000,77500,75,10),
]
CUSTOMERS = [('Walk-in customer',''),('Farah Ahmed','03001230001'),('Omar Raza','03001230002'),('Hina Malik','03001230003'),('Zainab Sheikh','03001230004')]
SUPPLIERS = [('Karachi Wholesale Foods','021-111-222333',3),('Metro FMCG Distributors','021-111-222444',5),('Fresh Supply Traders','021-111-222555',2)]

async def seed_commerce(conn):
    """Add public storefront demo data without overwriting a merchant's later edits."""
    await conn.execute('''INSERT INTO storefronts(tenant,slug,title,description,published)
        VALUES($1,$2,$3,$4,true) ON CONFLICT(tenant) DO NOTHING''',
        TENANT,'stockdesk-demo-market','StockDesk Demo Market',
        'Explore a sample neighborhood retail catalog. All orders are demonstrations, not real purchases.')
    # This sample tenant is isolated and explicitly opt-in.
    for sku,*_ in PRODUCTS[:12]:
        await conn.execute('''INSERT INTO storefront_listings(tenant,product,published,featured)
          VALUES($1,$2,true,$3) ON CONFLICT(tenant,product) DO NOTHING''',
          TENANT,uid('product:'+sku),sku in ('GROC-001','GROC-003','GROC-005'))


async def seed():
    if os.environ.get('APP_ENV', 'development').strip().lower() == 'production':
        raise SystemExit('Demo seeding is disabled when APP_ENV=production.')
    if os.environ.get('DEMO_SEED_CONFIRM') != 'I_UNDERSTAND_THIS_IS_DEMO_DATA':
        raise SystemExit('Refused: set DEMO_SEED_CONFIRM=I_UNDERSTAND_THIS_IS_DEMO_DATA')
    pwd = os.environ.get('DEMO_PASSWORD', '')
    if len(pwd) < 14 or len(pwd) > 128:
        raise SystemExit('Set DEMO_PASSWORD to a unique password of 14-128 characters; do not use a real user password.')
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise SystemExit('DATABASE_URL is required. Start backend once to apply migrations before seeding.')
    password_hash = await hash_password(pwd)
    conn = await asyncpg.connect(dsn, command_timeout=60)
    try:
        async with conn.transaction():
            # Guard against concurrent seed runs, and preserve existing demo account state.
            await conn.execute('SELECT pg_advisory_xact_lock($1)', 1390139)
            if await conn.fetchval('SELECT 1 FROM tenants WHERE id=$1', TENANT):
                await seed_commerce(conn)
                print('Demo tenant already exists: storefront demo data verified without modifying other records.')
                return
            await conn.execute('INSERT INTO tenants(id,name,currency,address,tax_number) VALUES($1,$2,$3,$4,$5)',TENANT,'StockDesk Demo Retail Group','PKR','Karachi, Pakistan','DEMO-NOT-TAX-REGISTERED')
            for key, name, role in STAFF:
                user_id=uid('user:'+key)
                email=f'demo.{key}@stockdesk.example'
                existing=await conn.fetchval('SELECT id FROM users WHERE email=$1',email)
                if existing and existing!=user_id:
                    raise RuntimeError(f'Email already belongs to another user: {email}')
                await conn.execute('INSERT INTO users(id,email,name,password_hash) VALUES($1,$2,$3,$4) ON CONFLICT(id) DO NOTHING',user_id,email,name,password_hash)
                await conn.execute('INSERT INTO members(id,tenant,user_id,role) VALUES($1,$2,$3,$4)',uid('member:'+key),TENANT,user_id,role)
            owner=uid('user:owner')
            cashier=uid('user:cashier')
            for code, name, kind, address in LOCATIONS:
                await conn.execute('INSERT INTO store_locations(id,tenant,code,name,kind,address) VALUES($1,$2,$3,$4,$5,$6)',uid('location:'+code),TENANT,code,name,kind,address)
            for index,(sku,barcode,name,category,price,cost,opening,reorder) in enumerate(PRODUCTS):
                pid=uid('product:'+sku)
                cat_code='pantry' if category=='Pantry' else 'general'
                cat_id=await conn.fetchval('SELECT id FROM lookups WHERE tenant=$1 AND kind=$2 AND code=$3',TENANT,'category',cat_code)
                unit_id=await conn.fetchval('SELECT id FROM lookups WHERE tenant=$1 AND kind=$2 AND code=$3',TENANT,'unit','piece')
                await conn.execute('INSERT INTO products(id,tenant,sku,barcode,name,category,price,cost,reorder,category_id,unit_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)',pid,TENANT,sku,barcode,name,category,price,cost,reorder,cat_id,unit_id)
                # Use the same stock ledger triggers as live movements, including batch balances.
                await conn.execute('INSERT INTO movements(id,tenant,product,quantity,type,notes,actor) VALUES($1,$2,$3,$4,$5,$6,$7)',uid('opening:'+sku),TENANT,pid,opening,'OPENING','Demo opening inventory',owner)
                allocation=[opening//2, opening//4, opening-opening//2-opening//4]
                for (code,_,_,_),qty in zip(LOCATIONS,allocation):
                    if qty:
                        await conn.execute('INSERT INTO warehouse_balances(tenant,location,product,quantity) VALUES($1,$2,$3,$4)',TENANT,uid('location:'+code),pid,qty)
                        await conn.execute('INSERT INTO warehouse_stock_assignments(id,tenant,request,location,product,quantity,actor) VALUES($1,$2,$3,$4,$5,$6,$7)',uid(f'assignment:{sku}:{code}'),TENANT,uid(f'assignment-request:{sku}:{code}'),uid('location:'+code),pid,qty,owner)
            for idx,(name,phone) in enumerate(CUSTOMERS):
                await conn.execute('INSERT INTO customers(id,tenant,name,phone) VALUES($1,$2,$3,$4)',uid(f'customer:{idx}'),TENANT,name,phone)
            for idx,(name,contact,lead_days) in enumerate(SUPPLIERS):
                await conn.execute('INSERT INTO suppliers(id,tenant,name,contact,lead_days) VALUES($1,$2,$3,$4,$5)',uid(f'supplier:{idx}'),TENANT,name,contact,lead_days)
            for idx in range(7):
                # Open purchase orders provide an immediate purchasing demo without inventing receipts.
                sku=PRODUCTS[idx][0]
                qty=10+idx*2
                cost=PRODUCTS[idx][5]
                po_id=uid(f'purchase:{idx}')
                await conn.execute('INSERT INTO purchase_orders(id,tenant,supplier,request,signature,reference,actor,order_total) VALUES($1,$2,$3,$4,$5,$6,$7,$8)',po_id,TENANT,uid(f'supplier:{idx%3}'),uid(f'po-request:{idx}'),'demo-seed-v139',f'DEMO-PO-{idx+1:04}',owner,qty*cost)
                await conn.execute('INSERT INTO purchase_lines(tenant,purchase,product,quantity,unit_cost) VALUES($1,$2,$3,$4,$5)',TENANT,po_id,uid('product:'+sku),qty,cost)
            payment_id=await conn.fetchval('SELECT id FROM lookups WHERE tenant=$1 AND kind=$2 AND code=$3',TENANT,'payment_method','cash')
            now=datetime.now(timezone.utc)
            for idx in range(36):
                item_indexes=[idx%len(PRODUCTS),(idx*3+7)%len(PRODUCTS)]
                item_indexes=list(dict.fromkeys(item_indexes))
                total=0
                lines=[]
                for offset,pidx in enumerate(item_indexes):
                    sku,barcode,name,category,price,cost,opening,reorder=PRODUCTS[pidx]
                    qty=1+(idx+offset)%3
                    lines.append((sku,name,price,cost,qty))
                    total+=price*qty
                sale_id=uid(f'sale:{idx}')
                created=now-timedelta(days=(35-idx),hours=(idx*7)%12)
                await conn.execute('''INSERT INTO sales(id,tenant,request,signature,invoice_number,customer,subtotal,total,tendered,payment,seller_name,seller_address,seller_tax_number,currency,actor,customer_id,paid_now,payment_method_id,cash_amount,created)
                  VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'cash',$10,$11,$12,'PKR',$13,$14,$15,$16,$17,$18)''',sale_id,TENANT,uid(f'sale-request:{idx}'),'demo-seed-v139',f'DEMO-INV-{idx+1:05}',CUSTOMERS[idx%len(CUSTOMERS)][0],total,total,total+5000,'StockDesk Demo Retail Group','Karachi, Pakistan','DEMO-NOT-TAX-REGISTERED',cashier,uid(f'customer:{idx%len(CUSTOMERS)}'),total,payment_id,total,created)
                for offset,(sku,name,price,cost,qty) in enumerate(lines):
                    pid=uid('product:'+sku)
                    await conn.execute('INSERT INTO sale_items(id,sale,tenant,product,name,sku,quantity,price,cost) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)',uid(f'sale-item:{idx}:{offset}'),sale_id,TENANT,pid,name,sku,qty,price,cost)
                    await conn.execute('INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,created) VALUES($1,$2,$3,$4,$5,$6,$7,$8)',uid(f'sale-movement:{idx}:{offset}'),TENANT,pid,-qty,'SALE',f'Demo invoice DEMO-INV-{idx+1:05}',cashier,created)
                    location=uid('location:DHA' if idx%2==0 else 'location:GUL')
                    updated=await conn.execute('UPDATE warehouse_balances SET quantity=quantity-$4 WHERE tenant=$1 AND location=$2 AND product=$3 AND quantity >= $4',TENANT,location,pid,qty)
                    if updated!='UPDATE 1':
                        raise RuntimeError('Demo stock allocation cannot cover sample sales')
            await conn.execute('UPDATE tenants SET invoice_seq=$2 WHERE id=$1',TENANT,36)
            await seed_commerce(conn)
            await conn.execute('INSERT INTO audit(id,tenant,actor,action,details) VALUES($1,$2,$3,$4,$5)',uid('seed-audit'),TENANT,owner,'demo_seed','StockDesk demo tenant generated with synthetic data; not actual financial or fiscal activity')
        print('Created isolated demo tenant: StockDesk Demo Retail Group')
        print('Login emails: ' + ', '.join(f'demo.{key}@stockdesk.example ({role})' for key,_,role in STAFF))
        print('Use your DEMO_PASSWORD value for all four accounts. Do not publish these accounts to the internet.')
        print('Created 2 retail stores, 1 warehouse, 20 products, 5 customers, 3 suppliers, 7 POs, 36 invoices.')
    finally:
        await conn.close()

if __name__=='__main__':
    asyncio.run(seed())
