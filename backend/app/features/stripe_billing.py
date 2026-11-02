"""Optional Stripe Billing integration; never trust browser return redirects as payment evidence."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from ..rules import fail


def webhook_event(raw: bytes, signature: str, secret: str, now: int | None = None) -> dict:
    """Verify Stripe's signed payload (multiple v1 signatures, five-minute skew)."""
    if not secret or not signature or len(raw)>256_000:
        fail('Invalid webhook message',400)
    values={}
    for field in signature.split(','):
        key, sep, value=field.partition('=')
        if sep and key in ('t','v1'):
            values.setdefault(key,[]).append(value)
    try:
        stamp=int(values.get('t',[''])[0])
    except ValueError:
        fail('Invalid webhook timestamp',400)
    moment=int(time.time()) if now is None else now
    if abs(moment-stamp)>300:
        fail('Expired webhook timestamp',400)
    signed=str(stamp).encode()+b'.'+raw
    expected=hmac.new(secret.encode(),signed,hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected,v) for v in values.get('v1',[])):
        fail('Webhook signature verification failed',400)
    try:
        event=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        fail('Invalid webhook JSON',400)
    if not isinstance(event,dict) or not isinstance(event.get('id'),str) or not isinstance(event.get('type'),str):
        fail('Missing webhook event identity',400)
    return event


async def stripe_request(method: str, path: str, data: dict | None = None,
                         idempotency: str | None = None) -> dict:
    key=os.environ.get('STRIPE_SECRET_KEY','')
    if not key:
        fail('Stripe Billing is not configured',503)
    headers={'Authorization':'Bearer '+key}
    if idempotency:
        headers['Idempotency-Key']=idempotency
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response=await client.request(method,'https://api.stripe.com/v1/'+path.lstrip('/'),
                                          headers=headers,data=data)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError,httpx.HTTPStatusError,ValueError):
        # Do not leak Stripe credentials or raw provider error messages.
        fail('Payment provider request failed; retry using the same request ID',502)


def subscription_period(remote: dict):
    start=remote.get('current_period_start')
    end=remote.get('current_period_end')
    if not start or not end:
        items=remote.get('items',{}).get('data',[])
        if items:
            start=items[0].get('current_period_start')
            end=items[0].get('current_period_end')
    if not isinstance(start,int) or not isinstance(end,int) or start>=end:
        return None
    return (datetime.fromtimestamp(start,tz=timezone.utc),
            datetime.fromtimestamp(end,tz=timezone.utc))


def normalized_subscription_status(provider_status: str) -> str:
    return {'active':'active','trialing':'trial','past_due':'past_due',
            'unpaid':'past_due','incomplete':'past_due','incomplete_expired':'cancelled',
            'canceled':'cancelled','paused':'past_due'}.get(provider_status,'past_due')
