"""Production-safe primitives for operational workflows.

Money is integer minor units. Every write uses tenant authorization, CSRF and
an atomic database transaction. This deliberately does not claim to implement
fiscal certification, stock valuation, or an offline browser database.
"""
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field, model_validator
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, service, security
from ..rules import fail

router = APIRouter(prefix='/api/v1/tenants/{tenant}', tags=['Business operations'], dependencies=[Depends(authenticated)])

class Location(Contract):
    code: str = Field(min_length=1, max_length=30, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=120)
    kind: Literal['store','warehouse']
    address: str = Field(default='', max_length=500)

class TransferLine(Contract):
    product: Identifier
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)

class Transfer(Contract):
    request: Identifier
    source: Identifier
    destination: Identifier
    lines: list[TransferLine] = Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def check_lines(self):
        if self.source == self.destination or len({i.product for i in self.lines}) != len(self.lines):
            raise ValueError('Source and destination must differ and each product appear once')
        return self

class Serial(Contract):
    product: Identifier
    serial_number: str = Field(min_length=1,max_length=120)
    location: Identifier | None = None

class Account(Contract):
    code: str = Field(min_length=1,max_length=30,pattern=r'^[0-9A-Za-z_-]+$')
    name: str = Field(min_length=1,max_length=120)
    kind: Literal['asset','liability','equity','income','expense']

class JournalLine(Contract):
    account: Identifier
    debit: int = Field(default=0,strict=True,ge=0,le=100_000_000_000)
    credit: int = Field(default=0,strict=True,ge=0,le=100_000_000_000)

class Journal(Contract):
    request: Identifier
    memo: str = Field(min_length=1,max_length=500)
    reference: str = Field(default='',max_length=100)
    lines: list[JournalLine] = Field(min_length=2,max_length=100)
    @model_validator(mode='after')
    def balance(self):
        if any((l.debit>0)==(l.credit>0) for l in self.lines):
            raise ValueError('Exactly one of debit/credit must be positive on each line')
        if sum(l.debit for l in self.lines)!=sum(l.credit for l in self.lines):
            raise ValueError('Journal debit and credit totals must balance')
        return self

class WalletEntry(Contract):
    request: Identifier
    customer: Identifier
    amount: int = Field(strict=True,ge=-100_000_000_000,le=100_000_000_000)
    reason: str = Field(min_length=3,max_length=300)

@router.get('/locations')
async def locations(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant)
        return {'items': service.rows(await c.fetch('SELECT * FROM store_locations WHERE tenant=$1 ORDER BY code',tenant))}

@router.post('/locations',status_code=201)
async def create_location(tenant: str,payload: Location,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            identifier=service.uid()
            await c.execute('INSERT INTO store_locations(id,tenant,code,name,kind,address) VALUES($1,$2,$3,$4,$5,$6)',identifier,tenant,payload.code,payload.name,payload.kind,payload.address)
            await service.audit(c,tenant,user,'Location created',{'id':identifier,'code':payload.code})
            return {'id':identifier}

@router.get('/warehouse-stock')
async def warehouse_stock(tenant: str,user: User,location: str | None=None):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'stock')
        return {'items':service.rows(await c.fetch('SELECT * FROM warehouse_balances WHERE tenant=$1 AND ($2::text IS NULL OR location=$2) ORDER BY location,product LIMIT 1000',tenant,location))}

@router.post('/warehouse-transfers',status_code=201)
async def transfer(tenant: str,payload: Transfer,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'stock',lock=True)
            prior=await c.fetchrow('SELECT * FROM warehouse_transfer_headers WHERE tenant=$1 AND request=$2',tenant,payload.request)
            if prior:
                lines=await c.fetch('SELECT product,quantity FROM warehouse_transfer_lines WHERE tenant=$1 AND transfer=$2 ORDER BY product',tenant,prior['id'])
                expected=sorted([(l.product,l.quantity) for l in payload.lines])
                if (prior['source'],prior['destination'])!=(payload.source,payload.destination) or [(l['product'],l['quantity']) for l in lines]!=expected:
                    fail('Request ID already used for a different transfer',409)
                return {'id':prior['id'],'duplicate':True}
            for loc in (payload.source,payload.destination):
                if not await c.fetchval('SELECT 1 FROM store_locations WHERE tenant=$1 AND id=$2 AND active=true',tenant,loc):
                    fail('Active source/destination not found',404)
            for line in sorted(payload.lines,key=lambda item:item.product):
                # Atomic decrement guards concurrent transfers; no balance can be negative.
                result=await c.fetchval('UPDATE warehouse_balances SET quantity=quantity-$1 WHERE tenant=$2 AND location=$3 AND product=$4 AND quantity >= $1 RETURNING quantity',line.quantity,tenant,payload.source,line.product)
                if result is None:
                    fail('Insufficient stock in the source warehouse for '+line.product,409)
                await c.execute('INSERT INTO warehouse_balances(tenant,location,product,quantity) VALUES($1,$2,$3,$4) ON CONFLICT(tenant,location,product) DO UPDATE SET quantity=warehouse_balances.quantity+excluded.quantity',tenant,payload.destination,line.product,line.quantity)
            identifier=service.uid()
            await c.execute('INSERT INTO warehouse_transfer_headers(id,tenant,request,source,destination,actor) VALUES($1,$2,$3,$4,$5,$6)',identifier,tenant,payload.request,payload.source,payload.destination,user['email'])
            for line in payload.lines:
                await c.execute('INSERT INTO warehouse_transfer_lines(transfer,tenant,product,quantity) VALUES($1,$2,$3,$4)',identifier,tenant,line.product,line.quantity)
            await service.audit(c,tenant,user,'Warehouse transfer',{'id':identifier,'from':payload.source,'to':payload.destination})
            return {'id':identifier,'duplicate':False}

@router.get('/warehouse-transfers')
async def transfers(tenant: str,user: User,limit: int=Query(50,ge=1,le=100)):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'stock')
        return {'items':service.rows(await c.fetch('SELECT * FROM warehouse_transfer_headers WHERE tenant=$1 ORDER BY created DESC LIMIT $2',tenant,limit))}

@router.post('/serials',status_code=201)
async def register_serial(tenant: str,payload: Serial,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'stock',lock=True)
            if not await c.fetchval('SELECT 1 FROM products WHERE tenant=$1 AND id=$2',tenant,payload.product):
                fail('Product not found',404)
            if payload.location and not await c.fetchval('SELECT 1 FROM store_locations WHERE tenant=$1 AND id=$2 AND active',tenant,payload.location):
                fail('Location not found',404)
            identifier=service.uid()
            await c.execute('INSERT INTO product_serials(id,tenant,product,serial_number,location) VALUES($1,$2,$3,$4,$5)',identifier,tenant,payload.product,payload.serial_number,payload.location)
            await service.audit(c,tenant,user,'Serial registered',{'serial_id':identifier,'product':payload.product})
            return {'id':identifier}

@router.get('/serials')
async def serials(tenant: str,user: User,product: str | None=None):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'stock')
        return {'items':service.rows(await c.fetch('SELECT * FROM product_serials WHERE tenant=$1 AND ($2::text IS NULL OR product=$2) ORDER BY created DESC LIMIT 500',tenant,product))}

@router.post('/gl/accounts',status_code=201)
async def create_account(tenant: str,payload: Account,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            identifier=service.uid()
            await c.execute('INSERT INTO gl_accounts(id,tenant,code,name,kind) VALUES($1,$2,$3,$4,$5)',identifier,tenant,payload.code,payload.name,payload.kind)
            await service.audit(c,tenant,user,'GL account created',{'id':identifier,'code':payload.code})
            return {'id':identifier}

@router.get('/gl/accounts')
async def accounts(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'finance')
        return {'items':service.rows(await c.fetch('SELECT * FROM gl_accounts WHERE tenant=$1 ORDER BY code',tenant))}

@router.post('/gl/journals',status_code=201)
async def post_journal(tenant: str,payload: Journal,request: Request,user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            prior=await c.fetchrow('SELECT id,memo,reference FROM gl_journals WHERE tenant=$1 AND request=$2',tenant,payload.request)
            if prior:
                lines=await c.fetch('SELECT account,debit,credit FROM gl_entries WHERE tenant=$1 AND journal=$2 ORDER BY account,debit,credit',tenant,prior['id'])
                expected=sorted([(l.account,l.debit,l.credit) for l in payload.lines])
                if (prior['memo'],prior['reference'])!=(payload.memo,payload.reference) or [(l['account'],l['debit'],l['credit']) for l in lines]!=expected:
                    fail('Request ID already used for a different journal',409)
                return {'id':prior['id'],'duplicate':True}
            for account in {l.account for l in payload.lines}:
                if not await c.fetchval('SELECT 1 FROM gl_accounts WHERE tenant=$1 AND id=$2 AND active',tenant,account):
                    fail('Invalid or inactive GL account',404)
            identifier=service.uid()
            await c.execute('INSERT INTO gl_journals(id,tenant,request,memo,reference,actor) VALUES($1,$2,$3,$4,$5,$6)',identifier,tenant,payload.request,payload.memo,payload.reference,user['email'])
            for line in payload.lines:
                await c.execute('INSERT INTO gl_entries(journal,tenant,account,debit,credit) VALUES($1,$2,$3,$4,$5)',identifier,tenant,line.account,line.debit,line.credit)
            await service.audit(c,tenant,user,'GL journal posted',{'id':identifier,'amount':sum(l.debit for l in payload.lines)})
            return {'id':identifier,'duplicate':False}

@router.get('/gl/trial-balance')
async def trial_balance(tenant: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'finance')
        items=service.rows(await c.fetch('SELECT a.code,a.name,a.kind,COALESCE(sum(e.debit),0) AS debits,COALESCE(sum(e.credit),0) AS credits FROM gl_accounts a LEFT JOIN gl_entries e ON e.tenant=a.tenant AND e.account=a.id WHERE a.tenant=$1 GROUP BY a.id ORDER BY a.code',tenant))
        return {'items':items,'debits':sum(i['debits'] for i in items),'credits':sum(i['credits'] for i in items)}

@router.post('/wallet/entries',status_code=201)
async def wallet_entry(tenant: str,payload: WalletEntry,request: Request,user: User):
    security.csrf(request)
    if not payload.amount:
        fail('Amount must not be zero')
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            prior=await c.fetchrow('SELECT * FROM customer_wallet_entries WHERE tenant=$1 AND request=$2',tenant,payload.request)
            if prior:
                if (prior['customer'],prior['amount'],prior['reason'])!=(payload.customer,payload.amount,payload.reason):
                    fail('Request ID already used',409)
                return {'id':prior['id'],'duplicate':True}
            if not await c.fetchval('SELECT 1 FROM customers WHERE tenant=$1 AND id=$2 AND active',tenant,payload.customer):
                fail('Customer not found',404)
            # Tenant-level FOR UPDATE serializes wallet changes and prevents negative balances.
            balance=await c.fetchval('SELECT COALESCE(sum(amount),0) FROM customer_wallet_entries WHERE tenant=$1 AND customer=$2',tenant,payload.customer)
            if balance+payload.amount<0:
                fail('Insufficient wallet balance',409)
            identifier=service.uid()
            await c.execute('INSERT INTO customer_wallet_entries(id,tenant,customer,request,amount,reason,actor) VALUES($1,$2,$3,$4,$5,$6,$7)',identifier,tenant,payload.customer,payload.request,payload.amount,payload.reason,user['email'])
            await service.audit(c,tenant,user,'Wallet adjustment',{'id':identifier,'customer':payload.customer,'amount':payload.amount})
            return {'id':identifier,'balance':balance+payload.amount,'duplicate':False}

@router.get('/wallet/{customer}')
async def wallet(tenant: str,customer: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'sale')
        items=service.rows(await c.fetch('SELECT id,amount,reason,created FROM customer_wallet_entries WHERE tenant=$1 AND customer=$2 ORDER BY created DESC LIMIT 100',tenant,customer))
        balance=await c.fetchval('SELECT COALESCE(sum(amount),0) FROM customer_wallet_entries WHERE tenant=$1 AND customer=$2',tenant,customer)
        return {'balance':balance,'items':items}

class StockAssignment(Contract):
    request: Identifier
    location: Identifier
    product: Identifier
    quantity: Decimal = Field(gt=0,max_digits=15,decimal_places=3)

@router.post('/warehouse-stock/allocate',status_code=201)
async def allocate_stock(tenant: str,payload: StockAssignment,request: Request,user: User):
    """Assign legacy unlocated inventory without changing total on-hand stock."""
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'stock',lock=True)
            prior=await c.fetchrow('SELECT * FROM warehouse_stock_assignments WHERE tenant=$1 AND request=$2',tenant,payload.request)
            if prior:
                if (prior['location'],prior['product'],prior['quantity'])!=(payload.location,payload.product,payload.quantity):
                    fail('Request ID already used with different stock assignment',409)
                return {'id':prior['id'],'duplicate':True}
            if not await c.fetchval('SELECT 1 FROM store_locations WHERE tenant=$1 AND id=$2 AND active=true',tenant,payload.location):
                fail('Location not found',404)
            on_hand=await c.fetchval('SELECT stock FROM products WHERE tenant=$1 AND id=$2 AND active=true FOR UPDATE',tenant,payload.product)
            if on_hand is None:
                fail('Product not found',404)
            assigned=await c.fetchval('SELECT COALESCE(sum(quantity),0) FROM warehouse_balances WHERE tenant=$1 AND product=$2',tenant,payload.product)
            if assigned+payload.quantity>on_hand:
                fail('Cannot assign more inventory than total available stock',409)
            identifier=service.uid()
            await c.execute('INSERT INTO warehouse_stock_assignments(id,tenant,request,location,product,quantity,actor) VALUES($1,$2,$3,$4,$5,$6,$7)',identifier,tenant,payload.request,payload.location,payload.product,payload.quantity,user['email'])
            await c.execute('INSERT INTO warehouse_balances(tenant,location,product,quantity) VALUES($1,$2,$3,$4) ON CONFLICT(tenant,location,product) DO UPDATE SET quantity=warehouse_balances.quantity+excluded.quantity',tenant,payload.location,payload.product,payload.quantity)
            await service.audit(c,tenant,user,'Legacy stock allocated',{'location':payload.location,'product':payload.product,'quantity':str(payload.quantity)})
            return {'id':identifier,'duplicate':False}
