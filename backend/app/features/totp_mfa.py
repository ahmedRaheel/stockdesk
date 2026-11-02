"""RFC 6238-style HMAC-SHA1 TOTP, encrypted at rest, single-use and time bounded."""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote
from cryptography.fernet import Fernet,InvalidToken
from ..rules import fail


def cipher():
    key=os.environ.get('MFA_ENCRYPTION_KEY','')
    if not key:
        fail('Authenticator encryption is not configured',503)
    try:
        return Fernet(key.encode())
    except (ValueError,TypeError):
        fail('Invalid MFA_ENCRYPTION_KEY configuration',503)


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken,ValueError):
        fail('Authenticator key is unavailable or invalid',503)


def otp(secret, step):
    secret=secret.upper()
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8),casefold=True)
    digest=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest()
    offset=digest[-1]&15
    digits=(struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000
    return f'{digits:06d}'


def match_code(secret,code,when=None,last_step=-1):
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdigit():
        return None
    now=int(time.time() if when is None else when)//30
    for step in (now,now-1,now+1):
        if step>last_step and hmac.compare_digest(otp(secret,step),code):
            return step
    return None


def provisioning_uri(address,secret):
    label=quote('StockDesk:'+address,safe='')
    issuer=quote('StockDesk',safe='')
    return f'otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30'


async def enforce(c,user_id,code):
    """Use inside a caller-owned transaction; holds a row lock for code consumption."""
    row=await c.fetchrow('SELECT secret_enc,last_used_step FROM user_mfa WHERE user_id=$1 AND enabled FOR UPDATE',user_id)
    if not row:
        return False
    step=match_code(decrypt(row['secret_enc']),code,last_step=row['last_used_step'])
    if step is None:
        fail('Invalid or missing authenticator code',401)
    await c.execute('UPDATE user_mfa SET last_used_step=$1 WHERE user_id=$2',step,user_id)
    return True
