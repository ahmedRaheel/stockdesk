import hashlib,hmac,json,time
from datetime import date,timedelta
from fastapi import HTTPException
import pytest
from app.features.auto_ledger import sale_entries
from app.features.stripe_billing import webhook_event,subscription_period,normalized_subscription_status
from app.features.totp_mfa import otp,match_code,new_secret,encrypt,decrypt


def test_ledger_balances_partial_payment_tax_and_cost():
    lines=sale_entries(10900,6000,900,4500)
    assert sum(d for _,d,_ in lines)==sum(c for _,_,c in lines)==15400
    assert ('1100',4900,0) in lines
    assert ('2000',0,900) in lines


def test_ledger_rejects_bad_numbers():
    with pytest.raises(HTTPException): sale_entries(500,600,0,20)
    with pytest.raises(HTTPException): sale_entries(500,300,600,20)


def test_signed_stripe_webhook_uses_raw_body():
    event={'id':'evt_test_01','type':'customer.subscription.updated','data':{'object':{}}}
    body=json.dumps(event,separators=(',',':')).encode()
    stamp=1_700_000_000
    signature=hmac.new(b'whsec_unit_test',str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
    assert webhook_event(body,f't={stamp},v1={signature}','whsec_unit_test',stamp)==event
    with pytest.raises(HTTPException): webhook_event(body+b' ',f't={stamp},v1={signature}','whsec_unit_test',stamp)
    with pytest.raises(HTTPException): webhook_event(body,f't={stamp},v1={signature}','whsec_unit_test',stamp+301)


def test_stripe_status_translation():
    assert normalized_subscription_status('trialing')=='trial'
    assert normalized_subscription_status('unpaid')=='past_due'
    assert subscription_period({'current_period_start':1_700_000_000,'current_period_end':1_700_086_400}) is not None


def test_totp_replay_rejected():
    secret=new_secret();step=1_700_000_000//30;code=otp(secret,step)
    assert match_code(secret,code,when=1_700_000_000)==step
    assert match_code(secret,code,when=1_700_000_000,last_step=step) is None
    assert match_code(secret,'12abcd',when=1_700_000_000) is None


def test_totp_secret_encryption(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('MFA_ENCRYPTION_KEY',Fernet.generate_key().decode())
    secret=new_secret();encrypted=encrypt(secret)
    assert encrypted!=secret
    assert decrypt(encrypted)==secret
