"""Argon2 passwords and hashed, opaque, HttpOnly sessions; shared DB login limits."""

import asyncio, hashlib, secrets
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from . import config
from .rules import fail, password

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


async def hash_password(value):
    return await asyncio.to_thread(ph.hash, password(value))


async def verify_password(value, hashed):
    try:
        return await asyncio.to_thread(ph.verify, hashed, value)
    except VerificationError:
        return False


DUMMY_HASH = ph.hash(secrets.token_urlsafe(32))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_token(c, user_id, tenant_scope=None, pin_revision=None):
    token = secrets.token_urlsafe(40)
    await c.execute(
        "INSERT INTO sessions(token_hash,user_id,expires,tenant_scope,pin_revision) VALUES($1,$2,$3,$4,$5)",
        digest(token),
        user_id,
        datetime.now(timezone.utc)
        + timedelta(
            hours=min(config.SESSION_HOURS, 8) if tenant_scope else config.SESSION_HOURS
        ),
        tenant_scope,
        pin_revision,
    )
    return token


async def session(c, user_id, response, tenant_scope=None, pin_revision=None):
    token = await issue_token(c, user_id, tenant_scope, pin_revision)
    response.set_cookie(
        "stockdesk_session",
        token,
        max_age=(min(config.SESSION_HOURS, 8) if tenant_scope else config.SESSION_HOURS)
        * 3600,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def credential(request):
    # An explicit Authorization header never falls back to ambient browser cookies.
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or len(token) > 256:
            fail("Invalid bearer credential.", 401)
        return token
    return request.cookies.get("stockdesk_session", "")


async def identity(c, request):
    token = credential(request)
    u = await c.fetchrow(
        "SELECT u.*,s.tenant_scope,s.pin_revision FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires>now() AND u.active=true",
        digest(token),
    )
    if not u:
        fail("Sign in to continue.", 401)
    if u["tenant_scope"]:
        allowed = await c.fetchval(
            "SELECT 1 FROM members m JOIN cashier_pins p ON p.tenant=m.tenant AND p.user_id=m.user_id WHERE m.tenant=$1 AND m.user_id=$2 AND m.active AND m.role='Cashier' AND m.custom_role_id IS NULL AND p.revision=$3",
            u["tenant_scope"],
            u["id"],
            u["pin_revision"],
        )
        if u["is_admin"] or not allowed:
            fail("Cashier session revoked. Sign in again.", 401)
    return dict(u)


def csrf(request):
    # Bearer requests cannot authenticate with ambient cookies; identity validates token.
    if request.headers.get("authorization") is not None:
        credential(request)
        return
    if request.headers.get("origin") != config.APP_ORIGIN:
        fail("Invalid request origin.", 403)


async def login_limit(c, key):
    row = await c.fetchrow(
        "INSERT INTO login_limits(key,attempts,window_start) VALUES($1,1,now()) ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN login_limits.window_start<now()-interval '15 minutes' THEN 1 ELSE login_limits.attempts+1 END,window_start=CASE WHEN login_limits.window_start<now()-interval '15 minutes' THEN now() ELSE login_limits.window_start END RETURNING attempts",
        digest(key),
    )
    if row["attempts"] > 10:
        fail("Too many login attempts. Try again in 15 minutes.", 429)
