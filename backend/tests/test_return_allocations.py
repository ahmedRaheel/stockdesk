"""Batch-specific and credit returns reconcile stock, debt, installments and cash."""
import os
import uuid
from decimal import Decimal
import httpx
import pytest


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')
@pytest.mark.asyncio
async def test_batch_and_khata_adjustments():
    from app import config, db
    from app.main import app
    config.ADMIN_EMAIL = 'test-admin@example.com'
    config.ADMIN_PASSWORD = 'TestAdminPassword!2026'
    config.APP_ORIGIN = 'http://testserver'
    db.DATABASE_URL = os.environ['TEST_DATABASE_URL']
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.APP_ORIGIN, headers={'Origin':config.APP_ORIGIN}) as c:
            assert (await c.post('/api/auth/login', json=dict(email=config.ADMIN_EMAIL,password=config.ADMIN_PASSWORD))).status_code == 200
            async def old(action, **payload):
                r=await c.post('/api/workspace',json=dict(action=action,**payload))
                assert r.status_code == 200, r.text
                return r.json()
            tenant=(await old('tenant',name='Return allocation QA',currency='PKR'))['id']
            base=f'/api/v1/tenants/{tenant}'
            async def post(path,payload):
                r=await c.post(base+path,json=payload)
                assert r.status_code in (200,201),r.text
                return r.json()
            product=(await old('product',tenant=tenant,sku='MULTI',name='Two batches',category='General',price=1000,cost=200,initial=2,reorder=0))['id']
            await old('movement',tenant=tenant,product=product,request=uuid.uuid4().hex,type='IN',quantity=2,lot='SECOND',notes='Second lot')
            await post('/tills',dict(opening_cash=10000))
            sale=await old('checkout',tenant=tenant,request=uuid.uuid4().hex,items=[dict(id=product,quantity=4)],payment='cash',expected=4000,tendered=4000)
            url=f"/sales/{sale['id']}/adjustments"
            options=(await c.get(base+url+'/batches')).json()['items'][0]
            second=next(b for b in options['batches'] if b['lot']=='SECOND')
            first=next(b for b in options['batches'] if b['lot']!='SECOND')
            payload=dict(revision=0,returns=[dict(item=options['item'],quantity=1,reason='incorrect',restock=True,batches=[dict(batch=second['batch'],quantity=1)])])
            async def commit(path,body,**extra):
                quote=await post(path+'/preview',body)
                return await post(path,dict(**body,request=uuid.uuid4().hex,quote_token=quote['quote_token'],settlement='cash',**extra))
            result=await commit(url,payload)
            assert result['net']==-1000
            options=(await c.get(base+url+'/batches')).json()['items'][0]
            assert {b['batch']:Decimal(str(b['available'])) for b in options['batches']} == {first['batch']:2,second['batch']:1}
            # Double allocation and cross-batch over-return fail atomically.
            payload['revision']=1
            for batches in ([dict(batch=second['batch'],quantity=2)], [dict(batch='foreign',quantity=1)], [dict(batch=second['batch'],quantity=1)]*2):
                bad={**payload,'returns':[{**payload['returns'][0],'batches':batches}]}
                q=await post(url+'/preview',bad)
                r=await c.post(base+url,json=dict(**bad,request=uuid.uuid4().hex,quote_token=q['quote_token']))
                assert r.status_code in (400,409),r.text
            await commit(url,payload)
            options=(await c.get(base+url+'/batches')).json()['items'][0]
            assert next(b for b in options['batches'] if b['batch']==second['batch'])['available']==0
            # Selecting the first lot now must not skip it because earlier returns selected the other lot.
            payload['revision']=2
            payload['returns'][0]['batches']=[dict(batch=first['batch'],quantity=1)]
            await commit(url,payload)
            async with db.pool.acquire() as conn:
                assert await conn.fetchval('SELECT stock FROM stock_batches WHERE id=$1',second['batch'])==2
                assert await conn.fetchval('SELECT stock FROM stock_batches WHERE id=$1',first['batch'])==1
            # Fully credit sale + markup + recovery + partial credit + full return.
            customer=await post('/customers',dict(name='Credit customer',phone='03000000000'))
            async with db.pool.acquire() as conn:
                await conn.execute('UPDATE customers SET credit_enabled=true,credit_limit=100000 WHERE id=$1',customer['id'])
            sale=await old('checkout',tenant=tenant,request=uuid.uuid4().hex,items=[dict(id=product,quantity=3)],payment='cash',expected=3000,tendered=0,paid_now=0,customer_id=customer['id'],due_date='2099-01-01')
            url=f"/sales/{sale['id']}/adjustments"
            statement=(await c.get(base+f"/customers/{customer['id']}/statement")).json()
            rid=statement['documents'][0]['id']
            await post('/installment-plans',dict(receivable=rid,installments=3,markup=300,frequency='monthly',first_due='2099-01-01'))
            async with db.pool.acquire() as conn:
                cash=await conn.fetchval("SELECT id FROM lookups WHERE tenant=$1 AND kind='payment_method' AND code='cash'",tenant)
            await post('/recoveries',dict(customer=customer['id'],request=uuid.uuid4().hex,amount=500,method=cash,reference='Received'))
            item=(await c.get(base+f"/sales/{sale['id']}")).json()['items'][0]['id']
            payload=dict(revision=0,returns=[dict(item=item,quantity=1,reason='damaged',restock=False)])
            q=await post(url+'/preview',payload)
            assert q['debt_credit']==1000 and q['net']==0 and q['outstanding_after']==1800
            posted=dict(**payload,request=uuid.uuid4().hex,quote_token=q['quote_token'])
            result=await post(url,posted)
            assert await post(url,posted)==result
            st=(await c.get(base+f"/customers/{customer['id']}/statement")).json()
            assert st['balance']==1800
            assert sum(s['paid'] for s in st['schedule'])==500
            assert sum(s['credited'] for s in st['schedule'])==1000
            assert max(st['schedule'],key=lambda s:s['sequence'])['credited']==1000
            # Recovery after preview invalidates the quote rather than over-refunding.
            payload=dict(revision=1,returns=[dict(item=item,quantity=2,reason='opened',restock=False)])
            q=await post(url+'/preview',payload)
            await post('/recoveries',dict(customer=customer['id'],request=uuid.uuid4().hex,amount=800,method=cash,reference='Received again'))
            r=await c.post(base+url,json=dict(**payload,request=uuid.uuid4().hex,quote_token=q['quote_token']))
            assert r.status_code==409,r.text
            result=await commit(url,payload)
            assert result['debt_credit']==1000 and result['net']==-1000
            st=(await c.get(base+f"/customers/{customer['id']}/statement")).json()
            assert st['balance']==0
            assert sum(s['paid'] for s in st['schedule'])==1300
            assert sum(s['credited'] for s in st['schedule'])==2000
            assert all(s['amount']==s['paid']+s['credited'] for s in st['schedule'])
            # No payments: full return must explicitly waive residual markup, with no refund.
            await old('movement',tenant=tenant,product=product,request=uuid.uuid4().hex,type='IN',quantity=1,lot='NEW',notes='New stock')
            sale=await old('checkout',tenant=tenant,request=uuid.uuid4().hex,items=[dict(id=product,quantity=1)],payment='cash',expected=1000,tendered=0,paid_now=0,customer_id=customer['id'],due_date='2099-01-01')
            url=f"/sales/{sale['id']}/adjustments"
            st=(await c.get(base+f"/customers/{customer['id']}/statement")).json()
            rid=next(d['id'] for d in st['documents'] if d['sale']==sale['id'])
            await post('/installment-plans',dict(receivable=rid,installments=2,markup=100,frequency='monthly',first_due='2099-01-01'))
            item=(await c.get(base+f"/sales/{sale['id']}")).json()['items'][0]['id']
            result=await commit(url,dict(revision=0,returns=[dict(item=item,quantity=1,reason='expired')]))
            assert result['debt_credit']==1000 and result['debt_waiver']==100 and result['net']==0
            st=(await c.get(base+f"/customers/{customer['id']}/statement")).json()
            assert st['balance']==0
            assert any(e['kind']=='waiver' and e['amount']==-100 for e in st['entries'])
