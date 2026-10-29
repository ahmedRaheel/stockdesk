"""Balance-driven alerts and permission boundaries, exercised through HTTP."""
import os
import uuid
import json
from datetime import timedelta
import pytest
import httpx
from pydantic import ValidationError
from app.api.alerts import Rule
from app.features.finance_alerts import allowed_kinds
from app.rules import business_date


def test_financial_contracts():
    assert set(allowed_kinds('Stock Manager')) == {'low_stock', 'stock_out', 'expiry'}
    for fields in [dict(product='p'), dict(threshold=1), dict(minimum_amount='0.001'), dict(overdue_days=-1), dict(lookback_days=0)]:
        with pytest.raises(ValidationError):
            Rule(name='Bad',kind='customer_overdue',**fields)


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')
@pytest.mark.asyncio
async def test_financial_alerts():
    from app import db, config
    from app.main import app
    from app.features.alerts import worker_once
    config.ADMIN_EMAIL='test-admin@example.com'
    config.ADMIN_PASSWORD='TestAdminPassword!2026'
    config.APP_ORIGIN='http://testserver'
    db.DATABASE_URL=os.environ['TEST_DATABASE_URL']
    async with app.router.lifespan_context(app):
        transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as c:
            assert (await c.post('/api/auth/login',json=dict(email=config.ADMIN_EMAIL,password=config.ADMIN_PASSWORD))).status_code==200
            async def old(action,**kw):
                r=await c.post('/api/workspace',json=dict(action=action,**kw))
                assert r.status_code==200,r.text
                return r.json()
            tenant=(await old('tenant',name='Financial alerts',currency='PKR'))['id']
            other=(await old('tenant',name='Other',currency='PKR'))['id']
            base=f'/api/v1/tenants/{tenant}'
            async def post(path,data):
                r=await c.post(base+path,json=data)
                assert r.status_code in (200,201),r.text
                return r.json()
            async def inbox(status='open'):
                return (await c.get(base+'/alert-center?status='+status)).json()
            async def evaluate():
                return await post('/alert-center/evaluate',{})
            product=(await old('product',tenant=tenant,sku='ITEM',name='Item',category='General',price=1000,cost=200,initial=10,reorder=0))['id']
            customer=(await post('/customers',dict(name='Private customer',phone='03000000000')))['id']
            async with db.pool.acquire() as conn:
                await conn.execute('UPDATE customers SET credit_enabled=true,credit_limit=100000 WHERE id=$1',customer)
            await post('/tills',dict(opening_cash=10000))
            sale=await old('checkout',tenant=tenant,request=uuid.uuid4().hex,items=[dict(id=product,quantity=2)],payment='cash',expected=2000,tendered=0,paid_now=0,customer_id=customer,due_date='2099-01-01')
            async with db.pool.acquire() as conn:
                rid=await conn.fetchval('SELECT id FROM receivables WHERE sale=$1',sale['id'])
                await conn.execute('UPDATE receivables SET due_date=$1 WHERE id=$2',business_date()-timedelta(days=2),rid)
                method=await conn.fetchval("SELECT id FROM lookups WHERE tenant=$1 AND kind='payment_method' AND code='cash'",tenant)
                actor=await conn.fetchval('SELECT id FROM users WHERE email=$1',config.ADMIN_EMAIL)
                for ident,variance,days in [('short',-500,0),('surplus',500,0),('old',-500,40),('balanced',0,0)]:
                    await conn.execute("INSERT INTO till_sessions(id,tenant,actor,opening_cash,status,closed,expected_cash,counted_cash,variance) VALUES($1,$2,$3,1000,'closed',now()-($4::int*interval '1 day'),1000,$5,$6)",tenant+ident,tenant,actor,days,1000+variance,variance)
            supplier=(await post('/suppliers',dict(name='Private supplier',contact='',lead_days=7)))['id']
            po=(await post('/purchase-orders',dict(request=uuid.uuid4().hex,supplier=supplier,reference='PO',lines=[dict(product=product,quantity=2,unit_cost=500)])))['id']
            await post(f'/purchase-orders/{po}/receipts',dict(request=uuid.uuid4().hex,lines=[dict(product=product,quantity=2)]))
            bill=(await post('/payables',dict(request=uuid.uuid4().hex,purchase=po,invoice_number='SUP-PRIVATE',invoice_date=str(business_date()-timedelta(days=4)),due_date=str(business_date()-timedelta(days=2)),tax=0,lines=[dict(product=product,quantity=2,unit_cost=500)])))['id']
            rules={}
            for kind in ['customer_overdue','supplier_overdue','cash_variance','low_stock']:
                rules[kind]=(await post('/alert-center/rules',dict(name=kind,kind=kind,minimum_amount='0' if kind=='low_stock' else '5.00',escalate_after_minutes=1)))['id']
            assert (await evaluate())['opened']==4
            assert (await evaluate())['opened']==0
            episodes=(await inbox())['items']
            def details(a):return json.loads(a['details']) if isinstance(a['details'],str) else a['details']
            assert {a['entity']:details(a)['amount'] for a in episodes}=={rid:2000,bill:1000,tenant+'short':-500,tenant+'surplus':500}
            assert (await c.get(f'/api/v1/tenants/{other}/alert-center')).json()['total']==0
            email=uuid.uuid4().hex+'@example.com';password='StaffPassword2026!'
            await old('member',tenant=tenant,email=email,password=password,name='Stock staff',role='Stock Manager')
            async with httpx.AsyncClient(transport=transport,base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as staff:
                await staff.post('/api/auth/login',json=dict(email=email,password=password))
                path=base+'/alert-center'
                assert (await staff.get(path+'?status=all')).json()==dict(items=[],total=0)
                assert [r['kind'] for r in (await staff.get(path+'/rules')).json()['items']]==['low_stock']
                assert (await staff.post(path+'/evaluate',json={})).json()['evaluated']==1
                assert (await staff.post(path+'/rules',json=dict(name='No',kind='supplier_overdue'))).status_code==403
                assert (await staff.put(path+'/rules/'+rules['supplier_overdue'],json=dict(name='No',kind='low_stock',version=1))).status_code==404
                assert (await staff.post(path+'/'+episodes[0]['id']+'/acknowledge',json=dict(note='No'))).status_code==404
                for role,total in [('Manager',4),('Stock Manager',0)]:
                    async with db.pool.acquire() as conn:
                        await conn.execute('UPDATE members SET role=$1 WHERE tenant=$2 AND user_id=(SELECT id FROM users WHERE email=$3)',role,tenant,email)
                    assert (await staff.get(path)).json()['total']==total
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE inventory_alert_rules SET overdue_days=2 WHERE tenant=$1",tenant)
            assert (await evaluate())['resolved']==2
            async with db.pool.acquire() as conn:
                await conn.execute('UPDATE inventory_alert_rules SET overdue_days=0,last_evaluated=NULL WHERE tenant=$1',tenant)
            await worker_once()
            assert (await inbox())['total']==4
            for payment in [500,1500]:
                await post('/recoveries',dict(customer=customer,request=uuid.uuid4().hex,amount=payment,method=method,reference='Collected'))
                await post(f'/payables/{bill}/payments',dict(request=uuid.uuid4().hex,amount=500,method_id=method,reference='Paid',paid_on=str(business_date())))
                result=await evaluate()
                if payment==500:
                    amounts={a['entity']:details(a)['amount'] for a in (await inbox())['items']}
                    assert amounts[rid]==1500 and amounts[bill]==500
                else: assert result['resolved']==2
            cash=(await inbox())['items']
            await post('/alert-center/'+cash[0]['id']+'/acknowledge',dict(note='Investigating'))
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE inventory_alerts SET opened=now()-interval '2 minutes' WHERE tenant=$1 AND kind='cash_variance'",tenant)
            assert (await evaluate())['escalated']==1
            assert (await inbox('acknowledged'))['total']==1
            update=dict(name='cash_variance',kind='cash_variance',minimum_amount='5.01',version=1)
            for expected in [200,409]:
                assert (await c.put(base+'/alert-center/rules/'+rules['cash_variance'],json=update)).status_code==expected
            assert (await evaluate())['opened']==0
            assert not (await inbox())['items']
            assert (await c.post(base+'/alert-center/evaluate',json={},headers={'Origin':'https://evil.example'})).status_code==403
