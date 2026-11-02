"""FBR DI sandbox validation only. No production filing or certification claims."""
import hashlib
import json
import os
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import APIRouter,Depends,Request
from pydantic import Field
from .contracts import Contract,Identifier
from .router import authenticated,User
from .. import db,security,service
from ..rules import fail

router=APIRouter(prefix='/api/v1/tenants/{tenant}/fbr',tags=['FBR sandbox validation'],
                 dependencies=[Depends(authenticated)])
SANDBOX_VALIDATE='https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata_sb'


def cipher():
    key=os.environ.get('FBR_ENCRYPTION_KEY','')
    if not key:
        fail('FBR credential encryption is not configured',503)
    try:
        return Fernet(key.encode())
    except (ValueError,TypeError):
        fail('Invalid FBR encryption key',503)


class SandboxToken(Contract):
    token: str=Field(min_length=20,max_length=4096)

class ValidateInvoice(Contract):
    request: Identifier
    sale: Identifier
    invoice: dict


def required_fields(value):
    if not isinstance(value,dict):
        fail('Invoice must be a JSON object',422)
    required=['invoiceType','invoiceDate','sellerNTNCNIC','sellerBusinessName','sellerProvince',
              'sellerAddress','buyerRegistrationType','items']
    missing=[k for k in required if not value.get(k)]
    if missing:
        fail('Missing FBR invoice fields: '+', '.join(missing),422)
    if not isinstance(value['items'],list) or not 1<=len(value['items'])<=100:
        fail('Provide 1-100 invoice items',422)
    if len(json.dumps(value))>60_000:
        fail('Invoice payload too large',413)


@router.put('/sandbox-token')
async def configure(tenant: str,payload:SandboxToken,request:Request,user:User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'settings',lock=True)
            secret=cipher().encrypt(payload.token.encode()).decode()
            await c.execute('''INSERT INTO fbr_sandbox_credentials(tenant,token_enc,configured_by)
                VALUES($1,$2,$3) ON CONFLICT(tenant) DO UPDATE SET
                token_enc=excluded.token_enc,configured_by=excluded.configured_by,updated=now()''',
                tenant,secret,user['email'])
            await service.audit(c,tenant,user,'FBR sandbox credential updated',{'configured':True})
    return {'configured':True,'environment':'sandbox'}


@router.post('/sandbox/validate')
async def validate(tenant: str,payload:ValidateInvoice,request:Request,user:User):
    security.csrf(request)
    required_fields(payload.invoice)
    canonical=json.dumps(payload.invoice,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(canonical).hexdigest()
    async with db.pool.acquire() as c:
        async with c.transaction():
            business,_=await service.authorize(c,user,tenant,'settings',lock=True)
            if not await c.fetchval('SELECT 1 FROM sales WHERE tenant=$1 AND id=$2',tenant,payload.sale):
                fail('Sale not found',404)
            existing=await c.fetchrow('''SELECT payload_sha256,status,response,sale FROM fbr_sandbox_validations
                WHERE tenant=$1 AND request=$2''',tenant,payload.request)
            if existing:
                if existing['payload_sha256']!=digest or existing['sale']!=payload.sale:
                    fail('Request ID reused with different invoice',409)
                return {'status':existing['status'],'result':existing['response'],'duplicate':True}
            token=await c.fetchval('SELECT token_enc FROM fbr_sandbox_credentials WHERE tenant=$1',tenant)
            if not token:
                fail('Configure the FBR sandbox token first',409)
            seller_ntn=business.get('ntn') if isinstance(business,dict) else business['ntn']
            if seller_ntn and str(payload.invoice['sellerNTNCNIC']).strip()!=str(seller_ntn).strip():
                fail('Seller NTN does not match the business profile',409)
            await c.execute('''INSERT INTO fbr_sandbox_validations(id,tenant,sale,request,payload_sha256,status)
                VALUES($1,$2,$3,$4,$5,'pending')''',service.uid(),tenant,payload.sale,payload.request,digest)
    try:
        secret=cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        fail('FBR encryption key is incorrect',503)
    try:
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.post(SANDBOX_VALIDATE,headers={
                'Authorization':'Bearer '+secret,'Content-Type':'application/json'},content=canonical)
        response.raise_for_status()
        result=response.json()
        status='validated' if isinstance(result,dict) and (
            result.get('validationResponse',{}).get('statusCode') in ('00',0,'0')
            or result.get('validationResponse',{}).get('status')=='Valid') else 'rejected'
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        result={'message':'Provider response inconclusive. Reconcile with PRAL before resubmitting.'}
        status='uncertain'
    async with db.pool.acquire() as c:
        async with c.transaction():
            await c.execute('''UPDATE fbr_sandbox_validations SET response=$1::jsonb,status=$2
                WHERE tenant=$3 AND request=$4''',json.dumps(result),status,tenant,payload.request)
    return {'status':status,'result':result,'certified':False,'environment':'sandbox'}


@router.get('/sandbox/validations')
async def validations(tenant:str,user:User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'settings')
        return {'items':service.rows(await c.fetch('''SELECT sale,request,status,created
            FROM fbr_sandbox_validations WHERE tenant=$1 ORDER BY created DESC LIMIT 100''',tenant))}
