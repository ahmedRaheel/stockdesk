"""Independent discount/return decisions and owner-controlled enforcement."""
import json
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail
from ..features import transaction_approvals as approvals

router=APIRouter(prefix='/api/v1/tenants/{tenant}/transaction-approvals',dependencies=[Depends(authenticated)],tags=['Transaction approvals'])

class Policy(Contract):
    version: int = Field(strict=True,ge=1)
    discount_required: bool = Field(strict=True)
    void_required: bool = Field(strict=True)

class Submission(Contract):
    request: Identifier
    kind: Literal['discount','return','adjustment']
    sale: Identifier | None = None
    payload: dict

class Decision(Contract):
    decision: Literal['approved','rejected']
    note: str = Field(min_length=1,max_length=500)

@router.get('/policy')
async def policy(tenant: str,user: User):
    async with db.pool.acquire() as c:
        business,_=await service.authorize(c,user,tenant,'sale')
        return dict(version=business['transaction_policy_version'],discount_required=business['discount_approval_required'],void_required=business['void_approval_required'])

@router.put('/policy')
async def save_policy(tenant: str,user: User,body: Policy,request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            business,_=await service.authorize(c,user,tenant,'roles',lock=True)
            if body.version!=business['transaction_policy_version']:
                fail('Approval policy changed. Reload and try again.',409)
            await c.execute('UPDATE tenants SET discount_approval_required=$1,void_approval_required=$2,transaction_policy_version=transaction_policy_version+1 WHERE id=$3',body.discount_required,body.void_required,tenant)
            await service.audit(c,tenant,user,'Transaction approval policy updated',body.model_dump())
            return {'version':body.version+1,'discount_required':body.discount_required,'void_required':body.void_required}

@router.get('')
async def listing(tenant: str,user: User,offset: int=Query(0,ge=0,le=1000000),limit: int=Query(50,ge=1,le=100)):
    async with db.pool.acquire() as c:
        _,role=await service.authorize(c,user,tenant,'sale')
        permitted=service.grants(role)
        rows=await c.fetch("""SELECT id,kind,sale,summary,requester_email,status,decision_email,note,created,expires,decided,consumed
          FROM transaction_approvals WHERE tenant=$1 AND
          (requester=$2 OR (kind='discount' AND $3) OR (kind<>'discount' AND $4))
          ORDER BY created DESC,id LIMIT $5 OFFSET $6""",tenant,user['id'],'discount_approve' in permitted,'void_approve' in permitted,limit,offset)
        items=service.rows(rows)
        for item in items:
            if isinstance(item['summary'],str):
                item['summary']=json.loads(item['summary'])
        return {'items':items}

@router.post('')
async def submit(tenant: str,user: User,body: Submission,request: Request):
    security.csrf(request)
    value=approvals.normalized(body.kind,body.payload)
    if (body.kind=='discount') != (body.sale is None):
        fail('Choose an invoice only for a return approval.')
    if body.kind=='discount' and not value['discount']:
        fail('A manual discount is required for discount approval.')
    digest=approvals.fingerprint(body.kind,body.sale,value)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'sale' if body.kind=='discount' else 'return',lock=True)
            prior=await c.fetchrow('SELECT * FROM transaction_approvals WHERE tenant=$1 AND request=$2',tenant,body.request)
            if prior:
                if prior['fingerprint']!=digest or prior['requester']!=user['id']:
                    fail('Submission ID already used for different data.',409)
                return {'id':prior['id'],'status':prior['status']}
            summary={}
            if body.sale:
                sale=await c.fetchrow('SELECT * FROM sales WHERE tenant=$1 AND id=$2',tenant,body.sale)
                if not sale or sale['status']!='completed':
                    fail('Completed invoice not found.',404)
                summary={'invoice':sale['invoice_number'],'total':sale['total']}
            if body.kind=='adjustment':
                from .exchanges import prepare, Commit
                summary.update((await prepare(c,tenant,body.sale,Commit.model_validate({**value,'request':'approval-preview'})))[0])
                if summary['quote_token']!=value['quote_token']:
                    fail('Prices or invoice changed. Review a fresh preview.',409)
            elif body.kind=='discount':
                from ..features.taxation import preview
                quote=await preview(c,tenant,value)
                if quote['total']!=value['expected']:
                    fail('Prices changed. Refresh and review the cart total.',409)
                summary.update(total=quote['total'],discount=value['discount'],customer=value['customer'],items=[])
                for line in value['items']:
                    product=await c.fetchrow('SELECT name,sku FROM products WHERE tenant=$1 AND id=$2',tenant,line['id'])
                    if not product:
                        fail('Product not found.',404)
                    summary['items'].append({**dict(product),'quantity':line['quantity']})
            else:
                summary['reason']=value['reason']
            identifier=service.uid()
            await c.execute('INSERT INTO transaction_approvals(id,tenant,request,kind,sale,fingerprint,payload,summary,requester,requester_email) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',identifier,tenant,body.request,body.kind,body.sale,digest,json.dumps(value),json.dumps(summary),user['id'],user['email'])
            await service.audit(c,tenant,user,'Transaction approval requested',{'id':identifier,'kind':body.kind,'sale':body.sale})
            return {'id':identifier,'status':'pending'}

@router.post('/{identifier}/decision')
async def decide(tenant: str,identifier: str,user: User,body: Decision,request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'sale',lock=True)
            row=await c.fetchrow('SELECT * FROM transaction_approvals WHERE tenant=$1 AND id=$2 FOR UPDATE',tenant,identifier)
            if not row:
                fail('Approval request not found.',404)
            await service.authorize(c,user,tenant,'discount_approve' if row['kind']=='discount' else 'void_approve')
            if row['requester']==user['id']:
                fail('Another authorized user must approve this transaction.',403)
            if row['status']==body.decision and row['decision_by']==user['id'] and row['note']==body.note:
                return {'id':identifier,'status':row['status']}
            if row['status']!='pending' or row['expires'] <= await c.fetchval('SELECT now()'):
                fail('This approval is no longer pending or has expired.',409)
            await c.execute('UPDATE transaction_approvals SET status=$1,decision_by=$2,decision_email=$3,note=$4,decided=now() WHERE tenant=$5 AND id=$6',body.decision,user['id'],user['email'],body.note,tenant,identifier)
            await service.audit(c,tenant,user,'Transaction approval decided',{'id':identifier,'decision':body.decision,'note':body.note})
            return {'id':identifier,'status':body.decision}
