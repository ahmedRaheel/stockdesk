"""Z freezes evidence; later returns belong to the later operator till."""

import os, uuid, json, hashlib
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_x_z_freeze_returns_retries_scope():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as c:
            await c.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )

            async def old(action, **data):
                r = await c.post("/api/workspace", json=dict(action=action, **data))
                assert r.status_code == 200, r.text
                return r.json()

            t = (await old("tenant", name="XZ QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}"

            async def post(path, data):
                r = await c.post(base + path, json=data)
                assert r.status_code == 200, r.text
                return r.json()

            async def report(sid, kind):
                r = await c.get(base + f"/tills/{sid}/reports/{kind}")
                assert r.status_code == 200, r.text
                return r.json()

            pid = (
                await old(
                    "product",
                    tenant=t,
                    sku="XZ",
                    name="XZ item",
                    category="General",
                    price=1000,
                    cost=200,
                    initial=20,
                    reorder=0,
                )
            )["id"]
            first = (await post("/tills", {"opening_cash": 1000}))["id"]
            sale = await post(
                "/sales",
                {
                    "request": uuid.uuid4().hex,
                    "items": [{"id": pid, "quantity": 2}],
                    "payment": "cash",
                    "tax_bps": 1000,
                    "expected": 2200,
                    "tendered": 2500,
                },
            )
            x = await report(first, "X")
            assert (
                x["report"]["totals"]["gross_sales"] == 2200
                and x["report"]["totals"]["expected_cash"] == 3200
            )
            assert (await c.get(base + f"/tills/{first}/reports/Z")).status_code == 409
            await post(f"/tills/{first}/close", {"counted_cash": 3200})
            z = await report(first, "Z")
            assert z["report"]["number"] == 1
            assert (
                z["digest"]
                == hashlib.sha256(
                    json.dumps(
                        z["report"], sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
            )
            await post(f"/tills/{first}/close", {"counted_cash": 3200})
            assert await report(first, "Z") == z
            assert (await c.get(base + f"/tills/{first}/reports/X")).status_code == 409
            second = (await post("/tills", {"opening_cash": 3000}))["id"]
            receipt = (await c.get(base + f"/sales/{sale['id']}")).json()
            body = {
                "revision": 0,
                "returns": [
                    {
                        "item": receipt["items"][0]["id"],
                        "quantity": 1,
                        "reason": "damaged",
                    }
                ],
            }
            url = f"/sales/{sale['id']}/adjustments"
            q = await post(url + "/preview", body)
            req = {
                **body,
                "request": uuid.uuid4().hex,
                "quote_token": q["quote_token"],
                "settlement": "cash",
            }
            await post(url, req)
            await post(url, req)
            x = await report(second, "X")
            tot = x["report"]["totals"]
            assert (
                tot["gross_sales"] == 0
                and tot["returns"] == 1100
                and tot["return_tax"] == 100
                and tot["expected_cash"] == 1900
            )
            assert len(x["report"]["returns"]) == 1 and await report(first, "Z") == z
            legacy = await post(
                "/sales",
                {
                    "request": uuid.uuid4().hex,
                    "items": [{"id": pid, "quantity": 1}],
                    "payment": "cash",
                    "expected": 1000,
                    "tendered": 1000,
                },
            )
            await post(
                f"/sales/{legacy['id']}/returns", {"reason": "Entire invoice incorrect"}
            )
            await post(
                f"/sales/{legacy['id']}/returns", {"reason": "Entire invoice incorrect"}
            )
            x = await report(second, "X")
            tot = x["report"]["totals"]
            assert (
                tot["gross_sales"] == 1000
                and tot["returns"] == 2100
                and tot["expected_cash"] == 2900
            )
            await post(
                f"/tills/{second}/cash-movements",
                {
                    "request": uuid.uuid4().hex,
                    "type": "OUT",
                    "amount": 1000,
                    "reason": "Legacy refund paid",
                },
            )
            await post(f"/tills/{second}/close", {"counted_cash": 1900})
            z2 = await report(second, "Z")
            assert (
                z2["report"]["number"] == 2
                and z2["report"]["totals"]["expected_cash"] == 1900
            )
            async with db.pool.acquire() as conn:
                import asyncpg

                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        "UPDATE till_z_reports SET digest=$1 WHERE tenant=$2",
                        "tampered",
                        t,
                    )
            other = (await old("tenant", name="Other XZ", currency="PKR"))["id"]
            assert (
                await c.get(f"/api/v1/tenants/{other}/tills/{first}/reports/Z")
            ).status_code == 404
