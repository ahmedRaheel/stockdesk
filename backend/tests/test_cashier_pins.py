"""PIN sessions are tenant-bound and never inherit elevated roles."""

import os, uuid
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_pin_scope_rotation_revocation_limits():
    from app import config, db, security
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        kw = dict(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        )
        async with httpx.AsyncClient(**kw) as owner, httpx.AsyncClient(
            **kw
        ) as cashier, httpx.AsyncClient(**kw) as terminal:

            async def login(c, email=config.ADMIN_EMAIL, pwd=config.ADMIN_PASSWORD):
                r = await c.post(
                    "/api/auth/login", json={"email": email, "password": pwd}
                )
                assert r.status_code == 200, r.text
                return r.json()["user"]["userId"]

            admin = await login(owner)
            await login(terminal)

            async def old(action, **data):
                r = await owner.post("/api/workspace", json=dict(action=action, **data))
                assert r.status_code == 200, r.text
                return r.json()

            t = (await old("tenant", name="PIN QA", currency="PKR"))["id"]
            other = (await old("tenant", name="Other PIN QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}"
            url = base + "/cashiers"
            email = uuid.uuid4().hex + "@example.com"
            pwd = "CashierPassword2026!"
            await old(
                "member",
                tenant=t,
                name="Cashier QA",
                email=email,
                password=pwd,
                role="Cashier",
            )
            uid = await login(cashier, email, pwd)
            async with db.pool.acquire() as c:
                await c.execute(
                    "INSERT INTO members(id,tenant,user_id,role) VALUES($1,$2,$3,'Owner')",
                    uuid.uuid4().hex,
                    other,
                    uid,
                )
            assert (
                await cashier.put(url + "/pin", json={"password": pwd, "pin": "12"})
            ).status_code == 422
            assert (
                await cashier.put(
                    url + "/pin",
                    json={"password": "WrongPassword2026!", "pin": "123456"},
                )
            ).status_code == 403
            assert (
                await cashier.put(
                    url + "/pin",
                    json={"password": pwd, "pin": "123456"},
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            r = await cashier.put(url + "/pin", json={"password": pwd, "pin": "123456"})
            assert r.status_code == 200, r.text
            assert (
                await owner.put(
                    url + "/pin",
                    json={"password": config.ADMIN_PASSWORD, "pin": "123456"},
                )
            ).status_code == 403
            roster = (await owner.get(url)).json()
            assert roster["items"][0]["pin_enabled"] and "pin_hash" not in str(roster)
            old_cookie = terminal.cookies.get("stockdesk_session")
            assert (
                await terminal.post(
                    url + "/switch", json={"user_id": uid, "pin": "000000"}
                )
            ).status_code == 401
            switched = await terminal.post(
                url + "/switch", json={"user_id": uid, "pin": "123456"}
            )
            assert switched.status_code == 200, switched.text
            assert terminal.cookies.get("stockdesk_session") != old_cookie
            async with db.pool.acquire() as c:
                assert not await c.fetchval(
                    "SELECT 1 FROM sessions WHERE token_hash=$1",
                    security.digest(old_cookie),
                )
            assert (await terminal.get("/api/auth/me")).json()["user"]["pinSession"]
            tenants = (await terminal.get("/api/v1/tenants")).json()["items"]
            assert len(tenants) == 1 and tenants[0]["id"] == t
            assert len((await terminal.get("/api/workspace")).json()["tenants"]) == 1
            assert (
                await terminal.get(f"/api/workspace?tenant={other}")
            ).status_code == 403
            assert (
                await terminal.get(f"/api/v1/tenants/{other}/products")
            ).status_code == 403
            assert (
                await terminal.put(
                    url + "/pin", json={"password": pwd, "pin": "654321"}
                )
            ).status_code == 403
            assert (
                await terminal.post(
                    base + "/products",
                    json={
                        "sku": "X",
                        "name": "X",
                        "category": "General",
                        "price": 100,
                        "cost": 0,
                        "initial": 0,
                        "reorder": 0,
                    },
                )
            ).status_code == 403
            assert (
                await cashier.put(url + "/pin", json={"password": pwd, "pin": "654321"})
            ).status_code == 200
            assert (await terminal.get("/api/auth/me")).status_code == 401
            await login(terminal)
            assert (
                await terminal.post(
                    url + "/switch", json={"user_id": uid, "pin": "123456"}
                )
            ).status_code == 401
            assert (
                await terminal.post(
                    url + "/switch", json={"user_id": uid, "pin": "654321"}
                )
            ).status_code == 200
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE members SET role='Owner' WHERE tenant=$1 AND user_id=$2",
                    t,
                    uid,
                )
            assert (await terminal.get(base + "/products")).status_code == 401
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE members SET role='Cashier' WHERE tenant=$1 AND user_id=$2",
                    t,
                    uid,
                )
            assert (await owner.delete(url + f"/{uid}/pin")).status_code == 200
            assert (await terminal.get("/api/auth/me")).status_code == 401
            await login(terminal)
            async with db.pool.acquire() as c:
                await c.execute(
                    "DELETE FROM login_limits WHERE key=$1",
                    security.digest("pin-source:" + admin),
                )
            for _ in range(10):
                assert (
                    await terminal.post(
                        url + "/switch", json={"user_id": "missing", "pin": "111111"}
                    )
                ).status_code == 401
            assert (
                await terminal.post(
                    url + "/switch", json={"user_id": "missing", "pin": "111111"}
                )
            ).status_code == 429
            async with db.pool.acquire() as c:
                audits = await c.fetch(
                    "SELECT details FROM audit WHERE tenant=$1 AND action LIKE 'Cashier%'",
                    t,
                )
                assert all(
                    "123456" not in r["details"]
                    and "654321" not in r["details"]
                    and pwd not in r["details"]
                    for r in audits
                )
