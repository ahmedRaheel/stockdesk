"""Approvals never grant reusable or self-approved transaction authority."""
import os
import uuid
import httpx
import pytest

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')
@pytest.mark.asyncio
async def test_independent_approvals_exact_payload_retries_and_revocation():
    from app import config,db
    from app.main import app
    config.ADMIN_EMAIL='test-admin@example.com';config.ADMIN_PASSWORD='TestAdminPassword!2026';config.APP_ORIGIN='http://testserver'
    db.DATABASE_URL=os.environ['TEST_DATABASE_URL']
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as owner, httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as manager:
            await owner.post('/api/auth/login',json=dict(email=config.ADMIN_EMAIL,password=config.ADMIN_PASSWORD))
            async def old(action,**kw):
                r=await owner.post('/api/workspace',json=dict(action=action,**kw));assert r.status_code==200,r.text;return r.json()
            tenant=(await old('tenant',name='Approval QA',currency='PKR'))['id'];base=f'/api/v1/tenants/{tenant}';url=base+'/transaction-approvals'
            email=uuid.uuid4().hex+'@example.com'
            await old('member',tenant=tenant,email=email,name='Approver',password='ApprovalPassword2026!',role='Manager')
            assert (await manager.post('/api/auth/login',json=dict(email=email,password='ApprovalPassword2026!'))).status_code==200
            pid=(await old('product',tenant=tenant,sku='A',name='Approval item',category='General',price=1000,cost=100,initial=10,reorder=0))['id']
            assert (await owner.put(url+'/policy',json=dict(version=1,discount_required=True,void_required=True))).status_code==200
            assert (await owner.put(url+'/policy',json=dict(version=1,discount_required=False,void_required=False))).status_code==409
            assert (await manager.put(url+'/policy',json=dict(version=2,discount_required=False,void_required=False))).status_code==403
            payload=dict(items=[dict(id=pid,quantity=2)],payment='cash',expected=1900,discount=100,tendered=2000)
            async def request(kind,body,sale=None):
                r=await owner.post(url,json=dict(request=uuid.uuid4().hex,kind=kind,payload=body,sale=sale));assert r.status_code==200,r.text;return r.json()['id']
            async def approve(identifier):
                r=await manager.post(url+f'/{identifier}/decision',json=dict(decision='approved',note='Reviewed exact transaction'));assert r.status_code==200,r.text
            sale_body={**payload,'request':uuid.uuid4().hex}
            assert (await owner.post(base+'/sales',json=sale_body)).status_code==409
            aid=await request('discount',payload)
            assert (await owner.post(url+f'/{aid}/decision',json=dict(decision='approved',note='Self approve'))).status_code==403
            await approve(aid);await approve(aid)
            # No approval on a changed amount or another cashier's transaction.
            assert (await owner.post(base+'/sales',json={**sale_body,'discount':200,'expected':1800,'approval_id':aid})).status_code==409
            assert (await manager.post(base+'/sales',json={**sale_body,'approval_id':aid})).status_code==409
            sale_body['approval_id']=aid
            done=await owner.post(base+'/sales',json=sale_body);assert done.status_code==200,done.text
            sale=done.json()
            again=await owner.post(base+'/sales',json=sale_body);assert again.status_code==200 and again.json()==sale
            assert (await owner.post(base+'/sales',json={**sale_body,'request':uuid.uuid4().hex})).status_code==409
            items=(await owner.get(url)).json()['items'];assert next(x for x in items if x['id']==aid)['status']=='consumed'
            # Legacy full-return API cannot bypass the independent void gate.
            ret={'reason':'Incorrect whole invoice'}
            assert (await owner.post(base+f"/sales/{sale['id']}/returns",json=ret)).status_code==409
            rid=await request('return',ret,sale['id']);await approve(rid)
            assert (await owner.post(base+f"/sales/{sale['id']}/returns",json={**ret,'approval_id':rid})).status_code==200
            # Expiration, rejection and revocation block otherwise matching requests.
            for mode in ('expired','rejected','inactive','revoked'):
                aid=await request('discount',payload)
                if mode=='rejected':
                    assert (await manager.post(url+f'/{aid}/decision',json=dict(decision='rejected',note='Not permitted'))).status_code==200
                else: await approve(aid)
                async with db.pool.acquire() as conn:
                    if mode=='inactive':await conn.execute('UPDATE users SET active=false WHERE email=$1',email)
                    if mode=='expired':await conn.execute("UPDATE transaction_approvals SET expires=now()-interval '1 minute' WHERE id=$1",aid)
                    if mode=='revoked':await conn.execute("UPDATE members SET active=false WHERE tenant=$1 AND user_id=(SELECT id FROM users WHERE email=$2)",tenant,email)
                denied=await owner.post(base+'/sales',json={**payload,'request':uuid.uuid4().hex,'approval_id':aid})
                assert denied.status_code in (403,409),denied.text
                if mode=='inactive':
                    async with db.pool.acquire() as conn:await conn.execute('UPDATE users SET active=true WHERE email=$1',email)
                if mode=='revoked':
                    async with db.pool.acquire() as conn:await conn.execute("UPDATE members SET active=true WHERE tenant=$1 AND user_id=(SELECT id FROM users WHERE email=$2)",tenant,email)
            # Invalid nested data is a 422, not a server exception.
            assert (await owner.post(url,json=dict(request='bad',kind='discount',payload={'unexpected':True}))).status_code==422
            # Partial returns/exchanges use the same approval gate and cannot self-approve.
            normal={**payload,'discount':0,'expected':2000,'request':uuid.uuid4().hex}
            created=await owner.post(base+'/sales',json=normal);assert created.status_code==200,created.text
            sale=created.json();su=base+f"/sales/{sale['id']}/adjustments"
            item=(await owner.get(base+f"/sales/{sale['id']}")).json()['items'][0]['id']
            adjust=dict(revision=0,returns=[dict(item=item,quantity=1,reason='damaged')])
            q=(await owner.post(su+'/preview',json=adjust)).json()
            body={**adjust,'quote_token':q['quote_token'],'settlement':'external','reference':'Manual refund'}
            assert (await owner.post(su,json={**body,'request':uuid.uuid4().hex})).status_code==409
            aid=await request('adjustment',body,sale['id']);await approve(aid)
            commit={**body,'request':uuid.uuid4().hex,'approval_id':aid}
            done=await owner.post(su,json=commit);assert done.status_code==200,done.text
            assert (await owner.post(su,json=commit)).json()==done.json()
            assert (await owner.post(url,json=dict(request='csrf',kind='discount',payload=payload),headers={'Origin':'http://evil.example'})).status_code==403
            other=(await old('tenant',name='Other approvals',currency='PKR'))['id']
            assert (await owner.post(f'/api/v1/tenants/{other}/transaction-approvals/{aid}/decision',json=dict(decision='approved',note='Cross tenant'))).status_code==404
