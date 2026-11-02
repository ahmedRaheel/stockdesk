"""Hosted subscription checkout, signed callbacks, and provider state reconciliation."""
import json
import os
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import config,db,security,service
from ..features.stripe_billing import (
    stripe_request,webhook_event,subscription_period,normalized_subscription_status,
)
from ..rules import fail

router=APIRouter(prefix='/api/v1/tenants/{tenant}/billing',
                 dependencies=[Depends(authenticated)],tags=['Stripe billing'])
webhooks=APIRouter(prefix='/api/v1/webhooks',tags=['Payment provider callbacks'])


class CheckoutStart(Contract):
    plan: Identifier
    request: Identifier


class StripePrice(Contract):
    price_id: str=Field(pattern=r'^price_[A-Za-z0-9]+$',min_length=8,max_length=120)


@router.put('/plans/{plan}/stripe-price')
async def connect_price(tenant: str,plan: str,payload: StripePrice,request: Request,user: User):
    security.csrf(request)
    if not user['is_admin']:
        fail('Platform administrator required',403)
    # Stripe price IDs cannot be arbitrary amounts; the amount/currency belong to Stripe.
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        selected=await c.fetchrow('SELECT monthly_price,currency FROM subscription_plans WHERE id=$1',plan)
    if not selected:
        fail('Plan not found',404)
    remote=await stripe_request('GET','prices/'+payload.price_id)
    recurrence=remote.get('recurring') or {}
    if (not remote.get('active') or recurrence.get('interval')!='month'
        or recurrence.get('interval_count',1)!=1
        or remote.get('currency','').upper()!=selected['currency'].upper()
        or remote.get('unit_amount')!=selected['monthly_price']):
        fail('Stripe price must match the active plan monthly amount and currency',409)
    async with db.pool.acquire() as c:
        await c.execute('UPDATE subscription_plans SET stripe_price_id=$1 WHERE id=$2',payload.price_id,plan)
    return {'ok':True}


@router.get('/plans')
async def available_plans(tenant:str,user:User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        plans=await c.fetch('''SELECT id,code,name,monthly_price,currency,max_stores
            FROM subscription_plans WHERE active=true AND stripe_price_id IS NOT NULL
            ORDER BY monthly_price,id''')
        current=await c.fetchrow('''SELECT s.status,s.ends,p.name AS plan_name FROM tenant_subscriptions s
            JOIN subscription_plans p ON p.id=s.plan WHERE s.tenant=$1''',tenant)
        return {'items':service.rows(plans),'subscription':dict(current) if current else None}


@router.post('/checkout')
async def create_checkout(tenant: str,payload: CheckoutStart,request: Request,user: User):
    security.csrf(request)
    if not os.environ.get('STRIPE_SECRET_KEY') or not os.environ.get('STRIPE_WEBHOOK_SECRET'):
        fail('Stripe Billing is not configured',503)
    if not config.APP_ORIGIN.startswith('https://'):
        fail('Stripe checkout requires HTTPS APP_ORIGIN',503)
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        plan=await c.fetchrow('''SELECT stripe_price_id FROM subscription_plans
            WHERE id=$1 AND active=true''',payload.plan)
        if not plan or not plan['stripe_price_id']:
            fail('This plan has no configured Stripe price',409)
        old=await c.fetchrow('SELECT session_id FROM stripe_checkout_sessions WHERE tenant=$1 AND request=$2',tenant,payload.request)
    if old:
        session=await stripe_request('GET','checkout/sessions/'+old['session_id'])
        return {'url':session['url'],'session_id':session['id'],'duplicate':True}
    session=await stripe_request('POST','checkout/sessions',{
        'mode':'subscription','line_items[0][price]':plan['stripe_price_id'],
        'line_items[0][quantity]':'1','client_reference_id':tenant,
        'metadata[tenant]':tenant,'metadata[plan]':payload.plan,
        'customer_email':user['email'],
        'success_url':config.APP_ORIGIN+'/billing?session_id={CHECKOUT_SESSION_ID}',
        'cancel_url':config.APP_ORIGIN+'/billing?cancelled=1',
    },idempotency='stockdesk-billing-'+tenant+'-'+payload.request)
    if not isinstance(session.get('id'),str) or not session.get('url','').startswith('https://checkout.stripe.com/'):
        fail('Payment provider did not return a valid hosted session',502)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            await c.execute('''INSERT INTO stripe_checkout_sessions(session_id,tenant,plan,request)
                VALUES($1,$2,$3,$4) ON CONFLICT(tenant,request) DO NOTHING''',
                session['id'],tenant,payload.plan,payload.request)
    return {'url':session['url'],'session_id':session['id'],'duplicate':False}


async def update_remote_subscription(c,tenant,plan,remote):
    period=subscription_period(remote)
    if not period:
        return False
    status=normalized_subscription_status(remote.get('status',''))
    await c.execute('''INSERT INTO tenant_subscriptions(tenant,plan,status,starts,ends)
        VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant) DO UPDATE SET
        plan=excluded.plan,status=excluded.status,starts=excluded.starts,ends=excluded.ends''',
        tenant,plan,status,*period)
    return True


@webhooks.post('/stripe')
async def stripe_webhook(request: Request):
    secret=os.environ.get('STRIPE_WEBHOOK_SECRET','')
    if not secret:
        fail('Stripe webhook is disabled',503)
    raw=await request.body()
    event=webhook_event(raw,request.headers.get('stripe-signature',''),secret)
    kind=event['type']
    entity=event.get('data',{}).get('object',{})
    if not isinstance(entity,dict):
        fail('Invalid Stripe event payload',400)
    # Fetch provider state BEFORE deduplicating. A transient failure must remain retryable.
    subscription_id=(entity.get('subscription') if kind=='checkout.session.completed'
                     else entity.get('id'))
    needs_remote=(kind=='checkout.session.completed' and entity.get('mode')=='subscription') or kind in (
        'customer.subscription.created','customer.subscription.updated','customer.subscription.deleted')
    remote=(await stripe_request('GET','subscriptions/'+subscription_id)
            if needs_remote and isinstance(subscription_id,str) else None)
    async with db.pool.acquire() as c:
        async with c.transaction():
            inserted=await c.fetchval('''INSERT INTO stripe_webhook_events(event_id,kind)
                VALUES($1,$2) ON CONFLICT(event_id) DO NOTHING RETURNING event_id''',event['id'],kind)
            if not inserted:
                return {'received':True,'duplicate':True}
            if kind=='checkout.session.completed' and entity.get('mode')=='subscription':
                matched=await c.fetchrow('''SELECT tenant,plan FROM stripe_checkout_sessions
                    WHERE session_id=$1''',entity.get('id'))
                if matched and isinstance(subscription_id,str):
                    await c.execute('''INSERT INTO stripe_subscription_links(subscription_id,tenant,plan)
                        VALUES($1,$2,$3) ON CONFLICT(tenant) DO UPDATE SET
                        subscription_id=excluded.subscription_id,plan=excluded.plan''',
                        subscription_id,matched['tenant'],matched['plan'])
                    if remote:
                        await update_remote_subscription(c,matched['tenant'],matched['plan'],remote)
            elif kind in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'):
                link=await c.fetchrow('''SELECT tenant,plan FROM stripe_subscription_links
                    WHERE subscription_id=$1''',subscription_id)
                if link and remote:
                    await update_remote_subscription(c,link['tenant'],link['plan'],remote)
    return {'received':True}
