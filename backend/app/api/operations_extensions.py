"""Offline replay, subscriptions, usage, forecasting and fiscal submission tracking.

Fiscal endpoints record evidence; they do not assert FBR approval or issue a
fabricated FBR invoice number. Replay uses existing idempotent checkout path.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from pydantic import Field, model_validator
from .contracts import Contract, Identifier, Checkout
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail

router = APIRouter(prefix='/api/v1/tenants/{tenant}',tags=['Extended business operations'],dependencies=[Depends(authenticated)])

class OfflineDevice(Contract):
    name: str=Field(min_length=1,max_length=100)

class OfflineSale(Contract):
    operation_id: Identifier
    sale: Checkout

class OfflineBatch(Contract):
    operations: list[OfflineSale] = Field(min_length=1, max_length=50)
    @model_validator(mode='after')
    def distinct_ids(self):
        if len({op.operation_id for op in self.operations}) != len(self.operations):
            raise ValueError('Operation identifiers must be unique within a batch')
        return self

class OfflineResolution(Contract):
    resolution: Literal['replaced','dismissed']
    replacement_sale: Identifier | None = None
    notes: str = Field(min_length=5, max_length=500)

    @model_validator(mode='after')
    def matching_reference(self):
        if (self.resolution == 'replaced') != (self.replacement_sale is not None):
            raise ValueError('A replacement sale ID is required only for a replaced operation.')
        return self


class Meter(Contract):
    request: Identifier
    metric: Literal['sale','api_call','storage_bytes','invoice']
    units: int=Field(strict=True,gt=0,le=100_000_000)

class Plan(Contract):
    code: str=Field(min_length=1,max_length=40,pattern=r'^[a-z0-9_-]+$')
    name: str=Field(min_length=1,max_length=100)
    monthly_price: int=Field(strict=True,ge=0,le=100_000_000_000)
    max_stores: int=Field(strict=True,ge=1,le=10000)

class Subscription(Contract):
    plan: Identifier
    status: Literal['trial','active','past_due','cancelled']
    starts: datetime
    ends: datetime
    @model_validator(mode='after')
    def validate_dates(self):
        if not self.starts.tzinfo or not self.ends.tzinfo or self.starts>=self.ends:
            raise ValueError('Provide timezone-aware start and end timestamps in ascending order')
        return self

class FiscalRecord(Contract):
    sale: Identifier
    status: Literal['pending']='pending'
    external_reference: str=Field(default='',max_length=120)
    provider: Literal['FBR']='FBR'
    request_payload: dict=Field(default_factory=dict)
    response_payload: dict=Field(default_factory=dict)

@router.post('/offline/devices',status_code=201)
async def register_device(tenant: str,payload: OfflineDevice,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'sale',lock=True)
            identifier=service.uid()
            await c.execute('INSERT INTO offline_devices(id,tenant,name,user_id) VALUES($1,$2,$3,$4)',identifier,tenant,payload.name,user['id'])
            await service.audit(c,tenant,user,'Offline device registered',{'device':identifier})
            return {'id':identifier}

@router.get('/offline/devices')
async def list_devices(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'sale')
        return {'items':service.rows(await c.fetch('SELECT id,name,active,created FROM offline_devices WHERE tenant=$1 AND user_id=$2 ORDER BY created DESC',tenant,user['id']))}

def offline_signature(sale: Checkout, tenant: str) -> tuple[dict,str]:
    canonical = sale.model_dump(mode='json')
    canonical.update(tenant=tenant, action='checkout')
    signature = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return canonical, signature


async def replay_one(c, user, tenant: str, device: str, operation: OfflineSale):
    canonical, signature = offline_signature(operation.sale, tenant)
    # Device ownership and tenant permissions are checked before this helper.
    previous = await c.fetchrow('''SELECT payload_hash,status,result FROM offline_operations
        WHERE tenant=$1 AND device=$2 AND operation_id=$3''', tenant,device,operation.operation_id)
    if previous:
        if previous['payload_hash'] != signature:
            fail('Offline operation ID reused with different sale data',409)
        return {'operation_id':operation.operation_id,'duplicate':True,'status':previous['status'],'result':json.loads(previous['result']) if isinstance(previous['result'],str) else previous['result']}
    # Keep business-rule rejection observable, but never persist a partially posted sale.
    # PostgreSQL savepoint rolls back checkout writes while retaining the parent transaction.
    try:
        async with c.transaction():
            result = await service.execute(c,user,canonical)
    except HTTPException as exc:
        if exc.status_code not in (400, 404, 409, 422):
            raise
        result = {'error':str(exc.detail),'http_status':exc.status_code,
                  'resolution':'Review stock, quote and payment; resubmit a corrected sale with a new operation ID.'}
        status = 'rejected'
    else:
        status = 'accepted'
    await c.execute('''INSERT INTO offline_operations(tenant,device,operation_id,payload_hash,status,result)
        VALUES($1,$2,$3,$4,$5,$6::jsonb)''',tenant,device,operation.operation_id,signature,status,json.dumps(result,default=str))
    return {'operation_id':operation.operation_id,'duplicate':False,'status':status,'result':result}


async def authorized_device(c, user, tenant, device):
    await service.authorize(c,user,tenant,'sale',lock=True)
    record = await c.fetchrow('''SELECT id FROM offline_devices WHERE tenant=$1 AND id=$2
        AND user_id=$3 AND active=true FOR UPDATE''',tenant,device,user['id'])
    if not record:
        fail('Offline device is inactive or belongs to another user',403)


@router.post('/offline/devices/{device}/replay')
async def replay(tenant: str,device: str,payload: OfflineSale,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await authorized_device(c,user,tenant,device)
            return await replay_one(c,user,tenant,device,payload)


@router.post('/offline/devices/{device}/replay-batch')
async def replay_batch(tenant: str,device: str,payload: OfflineBatch,request: Request,user: User):
    # Idempotent ordered replay; no offline card authorization.
    security.csrf(request)
    items=[]
    async with db.pool.acquire() as c:
        for op in payload.operations:
            async with c.transaction():
                await authorized_device(c,user,tenant,device)
                items.append(await replay_one(c,user,tenant,device,op))
    return {'items':items, 'accepted':sum(i['status']=='accepted' for i in items),
            'rejected':sum(i['status']=='rejected' for i in items)}

@router.get('/offline/devices/{device}/operations')
async def replay_history(tenant: str,device: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'sale')
        if not await c.fetchval('SELECT 1 FROM offline_devices WHERE tenant=$1 AND id=$2 AND user_id=$3',tenant,device,user['id']):
            fail('Device not found',404)
        return {'items':service.rows(await c.fetch('''SELECT o.operation_id,o.status,o.result,o.created,
            r.resolution,r.replacement_sale,r.notes AS resolution_notes,r.resolved_at
            FROM offline_operations o LEFT JOIN offline_operation_resolutions r
             ON r.tenant=o.tenant AND r.device=o.device AND r.operation_id=o.operation_id
            WHERE o.tenant=$1 AND o.device=$2 ORDER BY o.created DESC LIMIT 100''',tenant,device))}

@router.post('/offline/devices/{device}/operations/{operation_id}/resolve')
async def resolve_offline(tenant: str, device: str, operation_id: str,
                          payload: OfflineResolution, request: Request, user: User):
    # Resolve a rejected replay without rewriting evidence or submitting a new sale.
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await authorized_device(c,user,tenant,device)
            item = await c.fetchrow('''SELECT status FROM offline_operations
                WHERE tenant=$1 AND device=$2 AND operation_id=$3 FOR UPDATE''',
                tenant,device,operation_id)
            if not item or item['status']!='rejected':
                fail('Only rejected operations can be resolved.',409)
            old = await c.fetchrow('''SELECT resolution,replacement_sale,notes
                FROM offline_operation_resolutions
                WHERE tenant=$1 AND device=$2 AND operation_id=$3''',tenant,device,operation_id)
            if old:
                if (old['resolution'],old['replacement_sale'],old['notes']) != (payload.resolution,payload.replacement_sale,payload.notes):
                    fail('This offline conflict already has a different resolution.',409)
                return {'operation_id':operation_id,'resolution':old['resolution'],'duplicate':True}
            if payload.replacement_sale:
                sale = await c.fetchrow('''SELECT status FROM sales
                    WHERE tenant=$1 AND id=$2''',tenant,payload.replacement_sale)
                if not sale or sale['status']!='completed':
                    fail('Replacement must reference a completed POS sale in this business.',409)
            await c.execute('''INSERT INTO offline_operation_resolutions
                (tenant,device,operation_id,resolution,replacement_sale,notes,actor)
                VALUES($1,$2,$3,$4,$5,$6,$7)''',tenant,device,operation_id,
                payload.resolution,payload.replacement_sale,payload.notes,user['id'])
            await service.audit(c,tenant,user,'Offline replay conflict resolved',
                {'device':device,'operation':operation_id,'resolution':payload.resolution,
                 'replacement_sale':payload.replacement_sale})
    return {'operation_id':operation_id,'resolution':payload.resolution,'duplicate':False}


@router.post('/offline/devices/{device}/deactivate')
async def deactivate_device(tenant: str, device: str, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'sale',lock=True)
            updated=await c.fetchrow('''UPDATE offline_devices SET active=false
                WHERE tenant=$1 AND id=$2 AND user_id=$3 AND active=true RETURNING id''',
                tenant,device,user['id'])
            if not updated:
                fail('Active device not found for this user.',404)
            await service.audit(c,tenant,user,'Offline device deactivated',{'device':device})
    return {'ok':True}


@router.post('/usage',status_code=201)
async def record_usage(tenant: str,payload: Meter,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            prior=await c.fetchrow('SELECT units FROM tenant_usage_events WHERE tenant=$1 AND request=$2 AND metric=$3',tenant,payload.request,payload.metric)
            if prior is not None and prior['units']!=payload.units:
                fail('Usage request already applied with different units',409)
            if prior is None:
                await c.execute('INSERT INTO tenant_usage_events(id,tenant,request,metric,units) VALUES($1,$2,$3,$4,$5)',service.uid(),tenant,payload.request,payload.metric,payload.units)
            return {'ok':True,'duplicate':prior is not None}

@router.get('/usage')
async def usage(tenant: str,user: User,start: datetime|None=None,end: datetime|None=None):
    now=datetime.now(timezone.utc)
    start=start or now-timedelta(days=30)
    end=end or now
    if end<start or (end-start).days>366:
        fail('Invalid usage date range')
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        return {'items':service.rows(await c.fetch('SELECT metric,sum(units) AS units FROM tenant_usage_events WHERE tenant=$1 AND recorded>=$2 AND recorded<$3 GROUP BY metric ORDER BY metric',tenant,start,end))}

@router.post('/platform/plans',status_code=201)
async def create_plan(tenant: str,payload: Plan,request: Request,user: User):
    security.csrf(request)
    if not user['is_admin']:
        fail('Platform administrator required',403)
    async with db.pool.acquire() as c:
        async with c.transaction():
            identifier=service.uid()
            await c.execute('INSERT INTO subscription_plans(id,code,name,monthly_price,max_stores) VALUES($1,$2,$3,$4,$5)',identifier,payload.code,payload.name,payload.monthly_price,payload.max_stores)
            return {'id':identifier}

@router.get('/subscription')
async def get_subscription(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        value=await c.fetchrow('SELECT s.status,s.starts,s.ends,p.code,p.name,p.max_stores,p.monthly_price FROM tenant_subscriptions s JOIN subscription_plans p ON p.id=s.plan WHERE s.tenant=$1',tenant)
        return {'subscription':dict(value) if value else None}

@router.put('/subscription')
async def set_subscription(tenant: str,payload: Subscription,request: Request,user: User):
    security.csrf(request)
    if not user['is_admin']:
        fail('Platform administrator required',403)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,lock=True)
            if not await c.fetchval('SELECT 1 FROM subscription_plans WHERE id=$1 AND active',payload.plan):
                fail('Plan not found',404)
            await c.execute('INSERT INTO tenant_subscriptions(tenant,plan,status,starts,ends) VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant) DO UPDATE SET plan=excluded.plan,status=excluded.status,starts=excluded.starts,ends=excluded.ends',tenant,payload.plan,payload.status,payload.starts,payload.ends)
            await service.audit(c,tenant,user,'Subscription assigned',{'plan':payload.plan,'status':payload.status})
            return {'ok':True}

@router.get('/demand-forecast')
async def demand_forecast(tenant: str,user: User,days: int=Query(14,ge=1,le=90),lookback: int=Query(90,ge=28,le=365)):
    """Baseline daily demand projection using actual historical sale quantities.

    Do not label this statistical baseline as trained machine learning.
    """
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'forecast')
        records=await c.fetch('''SELECT p.id,p.name,p.stock,p.reorder,
            COALESCE(sum(si.quantity) FILTER (WHERE s.created>=now()-make_interval(days=>$2)),0) AS sold,
            count(DISTINCT s.created::date) FILTER (WHERE s.created>=now()-make_interval(days=>$2)) AS active_days
            FROM products p LEFT JOIN sale_items si ON si.tenant=p.tenant AND si.product=p.id
            LEFT JOIN sales s ON s.tenant=si.tenant AND s.id=si.sale AND s.status='completed'
            WHERE p.tenant=$1 AND p.active=true GROUP BY p.id ORDER BY p.name LIMIT 1000''',tenant,lookback)
        out=[]
        for r in records:
            daily=float(r['sold'])/lookback
            predicted=round(daily*days,3)
            out.append({'product':r['id'],'name':r['name'],'stock':float(r['stock']),
                        'historical_units':float(r['sold']),'predicted_units':predicted,
                        'suggested_reorder':max(0,round(predicted+float(r['reorder'])-float(r['stock']),3)),
                        'method':'historical_daily_average','lookback_days':lookback})
        return {'items':out,'horizon_days':days,'model':'baseline_not_ml'}

@router.post('/fiscal-submissions',status_code=201)
async def fiscal_submission(tenant: str,payload: FiscalRecord,request: Request,user: User):
    security.csrf(request)
    if len(json.dumps(payload.model_dump()))>16000:
        fail('Fiscal evidence too large',413)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            if not await c.fetchval('SELECT 1 FROM sales WHERE tenant=$1 AND id=$2',tenant,payload.sale):
                fail('Sale not found',404)
            if await c.fetchval('SELECT 1 FROM fiscal_submissions WHERE tenant=$1 AND sale=$2',tenant,payload.sale):
                fail('Submission already exists; keep the original fiscal audit record',409)
            identifier=service.uid()
            await c.execute('''INSERT INTO fiscal_submissions(id,tenant,sale,provider,status,external_reference,request_payload,response_payload)
                VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb)''',identifier,tenant,payload.sale,payload.provider,payload.status,payload.external_reference or None,json.dumps(payload.request_payload),json.dumps(payload.response_payload))
            await service.audit(c,tenant,user,'Fiscal submission evidence recorded',{'id':identifier,'sale':payload.sale,'status':payload.status})
            return {'id':identifier,'status':payload.status,'certified':False}

@router.get('/fiscal-submissions')
async def fiscal_submissions(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        return {'items':service.rows(await c.fetch('SELECT id,sale,provider,status,external_reference,created FROM fiscal_submissions WHERE tenant=$1 ORDER BY created DESC LIMIT 100',tenant))}


@router.get('/forecast-validation')
async def forecast_validation(tenant: str,user: User,days: int=Query(14,ge=1,le=90),
                              lookback: int=Query(120,ge=42,le=365),
                              limit: int=Query(100,ge=1,le=500)):
    # Zero-filled demand series and rolling out-of-sample accuracy by SKU.
    from datetime import date
    from ..features.forecast_validation import evaluate
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'forecast')
        products=await c.fetch('''SELECT id,name,stock,reorder FROM products
            WHERE tenant=$1 AND active=true ORDER BY name,id LIMIT $2''',tenant,limit)
        sales=await c.fetch('''SELECT si.product,s.created::date AS day,SUM(si.quantity) AS quantity
            FROM sale_items si JOIN sales s ON s.tenant=si.tenant AND s.id=si.sale
            WHERE si.tenant=$1 AND s.status='completed'
              AND s.created>=CURRENT_DATE-$2::integer
            GROUP BY si.product,s.created::date''',tenant,lookback)
    by_sku={(r['product'],r['day']):float(r['quantity']) for r in sales}
    today=date.today()
    output=[]
    for p in products:
        history=[(today-timedelta(days=i),by_sku.get((p['id'],today-timedelta(days=i)),0.0))
                 for i in range(lookback,0,-1)]
        report=evaluate(history,days)
        projected=report['predicted_units']
        output.append({'product':p['id'],'name':p['name'],'stock':float(p['stock']),
                       'suggested_reorder':max(0,round(projected+float(p['reorder'])-float(p['stock']),3)),
                       **report})
    return {'items':output,'lookback_days':lookback,'horizon_days':days,
            'note':'Backtest WAPE is historical and not a future accuracy guarantee.'}
