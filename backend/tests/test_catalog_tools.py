"""Stock conservation, expiry provenance and tenant boundaries for catalog tools."""
import os
import uuid
from decimal import Decimal
import httpx
import pytest


def test_variant_contracts():
    from app.api.catalog_tools import FamilyCreate, Variant, Component
    from pydantic import ValidationError
    assert FamilyCreate(request='x',name='Shirt',axes=[' Size ', 'COLOR']).axes==['size','color']
    for axes in (['size','Size'],[''],['a']*7):
        with pytest.raises(ValidationError): FamilyCreate(request='x',name='Shirt',axes=axes)
    with pytest.raises(ValidationError): Variant(version=0,attributes={'size':' '})
    with pytest.raises(ValidationError): Component(product='x',quantity='.0001')


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')
@pytest.mark.asyncio
async def test_variants_pack_bom_stock_and_provenance():
    from app import config,db
    from app.main import app
    config.ADMIN_EMAIL='test-admin@example.com';config.ADMIN_PASSWORD='TestAdminPassword!2026';config.APP_ORIGIN='http://testserver';db.DATABASE_URL=os.environ['TEST_DATABASE_URL']
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as c:
            await c.post('/api/auth/login',json=dict(email=config.ADMIN_EMAIL,password=config.ADMIN_PASSWORD))
            async def old(action,**kw):
                r=await c.post('/api/workspace',json=dict(action=action,**kw));assert r.status_code==200,r.text;return r.json()
            tenant=(await old('tenant',name='Catalog production QA',currency='PKR'))['id'];base=f'/api/v1/tenants/{tenant}/catalog-tools'
            async def post(path,payload):
                r=await c.post(base+path,json=payload);assert r.status_code==200,r.text;return r.json()
            async def product(sku,initial=0):return (await old('product',tenant=tenant,sku=sku,name=sku,category='General',price=1000,cost=100,initial=initial,reorder=0))['id']
            unit=await product('UNIT',24);pack=await product('PACK');other=await product('OTHER',10);kit=await product('KIT')
            family_body=dict(request=uuid.uuid4().hex,name='Shirts',axes=['size','color'])
            family=(await post('/families',family_body))['id']
            assert (await post('/families',family_body))['id']==family
            assert (await c.post(base+'/families',json={**family_body,'name':'Conflicting'})).status_code==409
            vurl=base+f'/families/{family}/variants/'
            assigned=await c.put(vurl+unit,json=dict(version=0,attributes={'size':'M','color':'Blue'}));assert assigned.status_code==200,assigned.text
            assert (await c.put(vurl+other,json=dict(version=0,attributes={'size':'m','color':'BLUE'}))).status_code==409
            assert (await c.put(vurl+unit,json=dict(version=0,attributes={'size':'L','color':'Blue'}))).status_code==409
            assert (await c.put(vurl+other,json=dict(version=0,attributes={'size':'L'}))).status_code==400
            assert (await c.put(vurl+other,json=dict(version=0,attributes={'size':'L','color':'Blue'}))).status_code==200
            detail=(await c.get(base+f'/families/{family}')).json();assert len(detail['items'])==2
            search=(await c.get(f'/api/v1/tenants/{tenant}/products',params={'q':'Shirts'})).json()
            assert search['total']==2 and all('Blue' in p['variant_label'] for p in search['items'])
            assert (await c.put(base+f'/families/{family}',json=dict(version=1,name='Shirts',active=False))).status_code==200
            assert (await c.put(vurl+pack,json=dict(version=0,attributes={'size':'XL','color':'Blue'}))).status_code==404
            assert (await c.get(base+f'/variants/{unit}')).json()['assignment']['version']==1
            recipe_body=dict(request=uuid.uuid4().hex,name='Six pack',kind='pack',output=pack,components=[dict(product=unit,quantity=6)])
            recipe=(await post('/recipes',recipe_body))['id'];url=f'/recipes/{recipe}'
            assert (await post('/recipes',recipe_body))['id']==recipe
            invalid={**recipe_body,'request':uuid.uuid4().hex,'output':other,'components':[dict(product=other,quantity=1)]}
            assert (await c.post(base+'/recipes',json=invalid)).status_code==400
            async def commit(path,body):
                quote=await post(path+'/preview',body);payload={**body,'request':uuid.uuid4().hex,'quote_token':quote['quote_token']}
                result=await post(path+'/jobs',payload)
                assert await post(path+'/jobs',payload)==result
                assert (await c.post(base+path+'/jobs',json={**payload,'note':'changed'})).status_code==409
                return result
            body=dict(version=1,direction='build',quantity=2,lot='PACK-A',note='Pack two')
            preview=await post(url+'/preview',body);assert Decimal(preview['inputs'][0]['quantity'])==12 and preview['input_catalog_cost']==1200
            result=await commit(url,body)
            async with db.pool.acquire() as conn:
                assert await conn.fetchval('SELECT stock FROM products WHERE id=$1',unit)==12
                assert await conn.fetchval('SELECT stock FROM products WHERE id=$1',pack)==2
                assert await conn.fetchval('SELECT count(*) FROM assembly_jobs WHERE tenant=$1',tenant)==1
                assert await conn.fetchval('SELECT sum(quantity) FROM movements WHERE notes=$1','Assembly '+result['id'])==Decimal('-10')
            unpack=await commit(url,dict(version=1,direction='unpack',quantity=1,lot='UNPACK-A',note='Open one pack'))
            assert Decimal(unpack['outputs'][0]['quantity'])==6
            async with db.pool.acquire() as conn:
                assert await conn.fetchval('SELECT stock FROM products WHERE id=$1',unit)==18
                assert await conn.fetchval('SELECT stock FROM products WHERE id=$1',pack)==1
            # Historical conversion factors are immutable after use.
            edit={k:v for k,v in recipe_body.items() if k!='request'};edit.update(version=1,active=True)
            assert (await c.put(base+url,json={**edit,'components':[dict(product=unit,quantity=7)]})).status_code==409
            assert (await c.put(base+url,json={**edit,'name':'Six unit pack'})).status_code==200
            assert (await c.post(base+url+'/preview',json=body)).status_code==409
            # Component movements after preview invalidate the entire quote.
            body['version']=2
            quote=await post(url+'/preview',body)
            await old('movement',tenant=tenant,product=unit,type='OUT',quantity=1,notes='Another use',request=uuid.uuid4().hex)
            assert (await c.post(base+url+'/jobs',json={**body,'request':uuid.uuid4().hex,'quote_token':quote['quote_token']})).status_code==409
            # BOM consumes multiple products atomically and cannot be unpacked.
            bom=(await post('/recipes',dict(request=uuid.uuid4().hex,name='Gift kit',kind='bom',output=kit,components=[dict(product=unit,quantity=2),dict(product=other,quantity=1)])))['id']
            job=dict(version=1,quantity=2,lot='KIT-A',note='Build kits')
            await commit(f'/recipes/{bom}',job)
            assert (await c.post(base+f'/recipes/{bom}/preview',json={**job,'direction':'unpack'})).status_code==400
            assert (await c.post(base+f'/recipes/{bom}/preview',json={**job,'quantity':1000})).status_code==409
            # Cycle A -> B -> A is rejected before any production is possible.
            assert (await c.post(base+'/recipes',json=dict(request=uuid.uuid4().hex,name='Cycle',kind='bom',output=unit,components=[dict(product=pack,quantity=1)]))).status_code==400
            # Expiry must flow from source to output; expired stock cannot be laundered.
            perishable=await product('PERISHABLE');output=await product('DATED-PACK')
            await old('movement',tenant=tenant,product=perishable,type='IN',quantity=10,notes='Dated source',request=uuid.uuid4().hex,lot='DATED',expires='2099-01-01')
            dated=(await post('/recipes',dict(request=uuid.uuid4().hex,name='Dated pack',kind='pack',output=output,components=[dict(product=perishable,quantity=2)])))['id']
            dated_body=dict(version=1,quantity=1,lot='D-OUT',note='Pack dated items')
            for expiry in (None,'2099-01-02'):
                assert (await c.post(base+f'/recipes/{dated}/preview',json={**dated_body,'expires':expiry})).status_code==400
            dated_body['expires']='2099-01-01'
            result=await commit(f'/recipes/{dated}',dated_body)
            assert result['earliest_input_expiry']=='2099-01-01'
            async with db.pool.acquire() as conn:
                await conn.execute('UPDATE stock_batches SET expires=current_date-1 WHERE tenant=$1 AND product=$2',tenant,perishable)
                counts=await conn.fetchval('SELECT count(*) FROM movements WHERE tenant=$1',tenant)
            assert (await c.post(base+f'/recipes/{dated}/preview',json=dated_body)).status_code==409
            async with db.pool.acquire() as conn:assert await conn.fetchval('SELECT count(*) FROM movements WHERE tenant=$1',tenant)==counts
            # Output rounded quantity cannot silently invent fractional whole units.
            assert (await c.post(base+url+'/preview',json={**body,'quantity':'.5'})).status_code==400
            # Cross-tenant SKU references and reads are isolated.
            foreign=(await old('tenant',name='Foreign catalog',currency='PKR'))['id']
            foreign_base=f'/api/v1/tenants/{foreign}/catalog-tools'
            assert (await c.get(foreign_base+f'/families/{family}')).status_code==404
            assert (await c.get(foreign_base+url)).status_code==404
            assert (await c.post(foreign_base+'/recipes',json=recipe_body)).status_code==404
            history=(await c.get(base+'/jobs')).json()['items'];assert len(history)==4
            assert all(j['movements'] and j['inputs'][0]['batches'] for j in history)
            # A database failure after input debits must roll back stock and job evidence.
            async with db.pool.acquire() as conn:
                before_stock=await conn.fetchval('SELECT stock FROM products WHERE id=$1',unit)
                before_jobs=await conn.fetchval('SELECT count(*) FROM assembly_jobs WHERE tenant=$1',tenant)
                await conn.execute("CREATE FUNCTION pg_temp.block_assembly_output() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.type='IN' AND NEW.notes LIKE 'Assembly %' THEN RAISE EXCEPTION 'QA output failure' USING ERRCODE='23514'; END IF; RETURN NEW; END $$")
                await conn.execute("CREATE TRIGGER qa_block_assembly_output BEFORE INSERT ON movements FOR EACH ROW EXECUTE FUNCTION pg_temp.block_assembly_output()")
            try:
                q=await post(url+'/preview',body)
                failed=await c.post(base+url+'/jobs',json={**body,'request':uuid.uuid4().hex,'quote_token':q['quote_token']})
                assert failed.status_code==409,failed.text
                async with db.pool.acquire() as conn:
                    assert await conn.fetchval('SELECT stock FROM products WHERE id=$1',unit)==before_stock
                    assert await conn.fetchval('SELECT count(*) FROM assembly_jobs WHERE tenant=$1',tenant)==before_jobs
            finally:
                async with db.pool.acquire() as conn:
                    await conn.execute('DROP TRIGGER qa_block_assembly_output ON movements')
            assert (await c.delete(vurl+other+'?version=9')).status_code==409
            assert (await c.delete(vurl+other+'?version=1')).status_code==200
            assert (await c.get(base+f'/variants/{other}')).json()=={'version':2,'assignment':None}
            assert (await c.put(vurl+other,json=dict(version=0,attributes={'size':'L','color':'Blue'}))).status_code in (404,409)
            assert (await c.put(base+f'/families/{family}',json=dict(version=2,name='Shirts',active=True))).status_code==200
            assert (await c.put(vurl+other,json=dict(version=2,attributes={'size':'L','color':'Blue'}))).status_code==200
            assert (await c.delete(vurl+other+'?version=1')).status_code==409
            # Cashiers can read family definitions, never create/convert inventory.
            email=uuid.uuid4().hex+'@example.com'
            await old('member',tenant=tenant,email=email,name='Cashier',password='CashierPassword2026!',role='Cashier')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=config.APP_ORIGIN,headers={'Origin':config.APP_ORIGIN}) as staff:
                await staff.post('/api/auth/login',json=dict(email=email,password='CashierPassword2026!'))
                assert (await staff.get(base+'/families')).status_code==200
                assert (await staff.post(base+'/families',json=family_body)).status_code==403
                assert (await staff.get(base+'/jobs')).status_code==403
                assert (await staff.post(base+url+'/preview',json=body)).status_code==403
            assert (await c.post(base+'/families',json=family_body,headers={'Origin':'http://wrong.example'})).status_code==403
