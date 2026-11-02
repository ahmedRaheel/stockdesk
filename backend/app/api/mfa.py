"""User-authenticated TOTP enrollment, confirmation, disable, and status endpoints."""
from fastapi import APIRouter,Depends,Request
from pydantic import Field
from .router import authenticated,User
from .contracts import Contract
from .. import db,security
from ..features.totp_mfa import new_secret,encrypt,decrypt,match_code,provisioning_uri,enforce
from ..rules import fail

router=APIRouter(prefix='/api/v1/auth/mfa',tags=['Multi-factor authentication'],
                 dependencies=[Depends(authenticated)])

class PasswordProof(Contract):
    password: str=Field(min_length=12,max_length=128)

class CodeProof(Contract):
    code: str=Field(pattern=r'^[0-9]{6}$')

class DisableProof(PasswordProof,CodeProof):
    pass

@router.get('/status')
async def status(user:User):
    async with db.pool.acquire() as c:
        row=await c.fetchrow('SELECT enabled FROM user_mfa WHERE user_id=$1',user['id'])
        return {'enabled':bool(row and row['enabled'])}

@router.post('/setup')
async def setup(payload:PasswordProof,request:Request,user:User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        if not await security.verify_password(payload.password,user['password_hash']):
            fail('Invalid password',401)
        async with c.transaction():
            existing=await c.fetchrow('SELECT enabled FROM user_mfa WHERE user_id=$1 FOR UPDATE',user['id'])
            if existing and existing['enabled']:
                fail('Disable existing authenticator before enrolling a replacement',409)
            secret=new_secret()
            await c.execute('''INSERT INTO user_mfa(user_id,secret_enc,enabled,enrolled,last_used_step)
                VALUES($1,$2,false,now(),-1) ON CONFLICT(user_id) DO UPDATE
                SET secret_enc=excluded.secret_enc,enabled=false,enrolled=now(),last_used_step=-1''',
                user['id'],encrypt(secret))
    return {'secret':secret,'provisioning_uri':provisioning_uri(user['email'],secret),
            'warning':'Store recovery access securely. A secret is returned only during setup.'}

@router.post('/enable')
async def enable(payload:CodeProof,request:Request,user:User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow('''SELECT secret_enc,enabled,enrolled FROM user_mfa
                WHERE user_id=$1 FOR UPDATE''',user['id'])
            if not row or row['enabled']:
                fail('No pending authenticator enrollment',409)
            await c.execute('DELETE FROM user_mfa WHERE user_id=$1 AND enrolled<now()-interval \'10 minutes\'',user['id'])
            if row['enrolled'].timestamp()<__import__('time').time()-600:
                fail('Authenticator enrollment expired',409)
            step=match_code(decrypt(row['secret_enc']),payload.code)
            if step is None:
                fail('Incorrect authenticator code',401)
            await c.execute('''UPDATE user_mfa SET enabled=true,enabled_at=now(),last_used_step=$1
                WHERE user_id=$2''',step,user['id'])
            await c.execute('DELETE FROM sessions WHERE user_id=$1',user['id'])
    return {'enabled':True,'signed_out':True}

@router.post('/disable')
async def disable(payload:DisableProof,request:Request,user:User):
    security.csrf(request)
    if not await security.verify_password(payload.password,user['password_hash']):
        fail('Invalid password',401)
    async with db.pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow('SELECT enabled FROM user_mfa WHERE user_id=$1 FOR UPDATE',user['id'])
            if not row or not row['enabled']:
                fail('Authenticator is not enabled',409)
            await enforce(c,user['id'],payload.code)
            await c.execute('DELETE FROM user_mfa WHERE user_id=$1',user['id'])
            await c.execute('DELETE FROM sessions WHERE user_id=$1',user['id'])
    return {'enabled':False,'signed_out':True}
