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


async def issue_token(c, user_id):
    token = secrets.token_urlsafe(40)
    await c.execute(
        "INSERT INTO sessions(token_hash,user_id,expires) VALUES($1,$2,$3)",
        digest(token),
        user_id,
        datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS),
    )
    return token


async def session(c, user_id, response):
    token = await issue_token(c, user_id)
    response.set_cookie(
        "stockdesk_session",
        token,
        max_age=config.SESSION_HOURS * 3600,
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
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires>now() AND u.active=true",
        digest(token),
    )
    if not u:
        fail("Sign in to continue.", 401)
    return u


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
