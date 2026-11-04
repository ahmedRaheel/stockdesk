"""Preview-first, single-transaction migration from arbitrary legacy retail CSV exports."""
import hashlib
import json
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field, model_validator
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, security, service
from ..features.catalog import save_product
from ..features.migration_parser import parse_csv
from ..rules import fail

router=APIRouter(prefix="/api/v1/tenants/{tenant}/migration-wizard",tags=["Store migration"],dependencies=[Depends(authenticated)])


class LegacyBatch(Contract):
    products_csv: str = Field(default='', max_length=250_000)
    customers_csv: str = Field(default='', max_length=250_000)
    suppliers_csv: str = Field(default='', max_length=250_000)
    location_id: str | None = Field(default=None,max_length=100)

    @model_validator(mode='after')
    def nonempty(self):
        if not any((self.products_csv.strip(),self.customers_csv.strip(),self.suppliers_csv.strip())):
            raise ValueError('Provide at least one CSV file.')
        return self


class Commit(LegacyBatch):
    request_id: Identifier
    preview_token: str=Field(min_length=64,max_length=64)


def fingerprint(tenant, data):
    fields=data.model_dump(exclude={'request_id','preview_token'})
    return hashlib.sha256(json.dumps({'tenant':tenant,'data':fields},sort_keys=True).encode()).hexdigest()


def parse_all(data):
    return {kind:parse_csv(getattr(data,kind+'_csv'),kind) for kind in ('products','customers','suppliers')}


@router.get('/history')
async def history(tenant: str, user: User, limit: int = Query(25, ge=1, le=100)):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'product')
        return {'items':service.rows(await c.fetch('''SELECT request_id,summary,actor,created
            FROM migration_batches WHERE tenant=$1 ORDER BY created DESC LIMIT $2''',tenant,limit))}


@router.post('/preview')
async def preview(tenant:str,payload:LegacyBatch,request:Request,user:User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'product')
        await service.authorize(c,user,tenant,'stock')
    grouped=parse_all(payload)
    return {'preview_token':fingerprint(tenant,payload),
            'counts':{kind:len(rows) for kind,rows in grouped.items()},
            'samples':{kind:[{k:str(v) for k,v in row.items()} for row in rows[:5]] for kind,rows in grouped.items()},
            'note':'Preview validates CSV syntax and values only. Commit validates live SKU, lookup and stock constraints in one database transaction.'}


@router.post('/commit',status_code=201)
async def commit(tenant:str,payload:Commit,request:Request,user:User):
    security.csrf(request)
    signature=fingerprint(tenant,payload)
    if payload.preview_token!=signature:
        fail('CSV data changed after preview. Preview again.',409)
    grouped=parse_all(payload)
    async with db.pool.acquire() as c:
        async with c.transaction():
            # All imported entities, opening movements and batch receipt share one transaction.
            await service.authorize(c,user,tenant,'product',lock=True)
            await service.authorize(c,user,tenant,'stock')
            previous=await c.fetchrow('SELECT signature,summary FROM migration_batches WHERE tenant=$1 AND request_id=$2',tenant,payload.request_id)
            if previous:
                if previous['signature']!=signature: fail('Import ID already used for different CSV files.',409)
                result=previous['summary']
                return {'duplicate':True,**(json.loads(result) if isinstance(result,str) else result)}
            location=None
            if payload.location_id:
                location=await c.fetchrow("SELECT id FROM store_locations WHERE tenant=$1 AND id=$2 AND active",tenant,payload.location_id)
                if not location: fail('Selected stock location is inactive or missing.',404)
            elif any(row['initial']>0 for row in grouped['products']):
                has_locations=await c.fetchval('SELECT 1 FROM store_locations WHERE tenant=$1 LIMIT 1',tenant)
                if has_locations: fail('Choose a store or warehouse for opening stock before importing.',422)
            result={kind:{'created':0,'skipped':0} for kind in grouped}
            # Supplier/customer updates are never silent; existing matches are left unchanged.
            for row in grouped['suppliers']:
                exists=await c.fetchval('SELECT 1 FROM suppliers WHERE tenant=$1 AND lower(name)=lower($2)',tenant,row['name'])
                if exists:
                    result['suppliers']['skipped']+=1
                    continue
                await c.execute('INSERT INTO suppliers(id,tenant,name,contact,lead_days) VALUES($1,$2,$3,$4,$5)',
                    service.uid(),tenant,row['name'],row['contact'],row['lead_days'])
                result['suppliers']['created']+=1
            for row in grouped['customers']:
                # A name alone is not a safe unique customer key; deduplicate only if phone exists.
                exists=(await c.fetchval('SELECT 1 FROM customers WHERE tenant=$1 AND phone=$2 AND lower(name)=lower($3)',tenant,row['phone'],row['name'])) if row['phone'] else None
                if exists:
                    result['customers']['skipped']+=1
                    continue
                await c.execute('INSERT INTO customers(id,tenant,name,phone,address) VALUES($1,$2,$3,$4,$5)',
                    service.uid(),tenant,row['name'],row['phone'],row['address'])
                result['customers']['created']+=1
            for row in grouped['products']:
                exists=await c.fetchval('SELECT 1 FROM products WHERE tenant=$1 AND sku=$2',tenant,row['sku'])
                if exists:
                    result['products']['skipped']+=1
                    continue
                category=await c.fetchrow("SELECT id,name FROM lookups WHERE tenant=$1 AND kind='category' AND code=$2 AND active",tenant,row['category_code'])
                unit=await c.fetchrow("SELECT id FROM lookups WHERE tenant=$1 AND kind='unit' AND code=$2 AND active",tenant,row['unit_code'])
                if not category or not unit:
                    fail(f"products row {row['_row']}: unknown category or unit code. Configure Lookups first.",422)
                product_id=(await save_product(c,user,{'action':'product','tenant':tenant,'sku':row['sku'],
                    'name':row['name'],'barcode':row['barcode'],'price':row['price'],'cost':row['cost'],
                    'initial':row['initial'],'reorder':row['reorder'],'category_id':category['id'],
                    'unit_id':unit['id']}))['id']
                if location and row['initial']>0:
                    await c.execute('''INSERT INTO warehouse_balances(tenant,location,product,quantity)
                         VALUES($1,$2,$3,$4)''',tenant,location['id'],product_id,row['initial'])
                result['products']['created']+=1
            await c.execute('INSERT INTO migration_batches(tenant,request_id,signature,summary,actor) VALUES($1,$2,$3,$4::jsonb,$5)',
                            tenant,payload.request_id,signature,json.dumps(result),user['email'])
            await service.audit(c,tenant,user,'Legacy CSV migration completed',{'request':payload.request_id,'counts':result})
    return {'duplicate':False,**result}
