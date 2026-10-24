"""Requires TEST_DATABASE_URL pointing at a disposable PostgreSQL database.
Also runs on PGlite's PostgreSQL protocol adapter for sequential SQL verification.
Never run against a real inventory database: migrations create test records.
"""

import os, uuid, asyncio
import pytest
import httpx

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a disposable PostgreSQL database",
)


@pytest.mark.asyncio
async def test_complete_inventory_flow():
    from app import config, db
    from app.main import app
    from app.service import uid

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    db.DATABASE_URL = os.getenv("TEST_DATABASE_URL")
    config.APP_ORIGIN = "http://testserver"
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as client:
            denied = await client.get("/api/workspace")
            assert denied.status_code == 401
            login = await client.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )
            assert login.status_code == 200, login.text

            async def post(action, tenant="", **kw):
                return await client.post(
                    "/api/workspace", json={"action": action, "tenant": tenant, **kw}
                )

            unique = uuid.uuid4().hex[:8]
            response = await post("tenant", name="Test Store " + unique, currency="PKR")
            assert response.status_code == 200, response.text
            a = response.json()["id"]
            other = (
                await post("tenant", name="Second Store " + unique, currency="USD")
            ).json()["id"]
            response = await post(
                "product",
                a,
                sku="SKU-1",
                barcode="123456789012",
                name="Keyboard",
                category="Hardware",
                price=10000,
                cost=6000,
                initial=5,
                reorder=2,
            )
            assert response.status_code == 200, response.text
            duplicate = await post(
                "product",
                a,
                sku="SKU-1",
                barcode="",
                name="Duplicate",
                category="Hardware",
                price=1,
                cost=0,
                initial=0,
                reorder=0,
            )
            assert duplicate.status_code == 400
            snapshot = await client.get("/api/workspace", params={"tenant": a})
            assert snapshot.status_code == 200, snapshot.text
            forecast = await client.get(
                "/api/forecasts", params={"tenant": a, "period": "last_week"}
            )
            assert forecast.status_code == 200, forecast.text
            assert forecast.json()["forecasts"][0]["next30"] is None
            data = snapshot.json()
            assert data["products"][0]["stock"] == 5
            assert data["salesChart"]["data"][0]["type"] == "bar"
            pid = data["products"][0]["id"]
            member_email = f"cashier-{unique}@example.com"
            member_password = "CashierPassword!2026"
            response = await post(
                "member",
                a,
                email=member_email,
                name="Cashier",
                password=member_password,
                role="Cashier",
            )
            assert response.status_code == 200, response.text
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Origin": "http://testserver"},
            ) as cashier:
                assert (
                    await cashier.post(
                        "/api/auth/login",
                        json={"email": member_email, "password": member_password},
                    )
                ).status_code == 200
                assert (
                    await cashier.get("/api/workspace", params={"tenant": other})
                ).status_code == 403
                assert (
                    await cashier.get("/api/forecasts", params={"tenant": a})
                ).status_code == 403
                assert (
                    await cashier.post(
                        "/api/workspace", json={"action": "product", "tenant": a}
                    )
                ).status_code == 403
                assert (
                    await cashier.post(
                        "/api/workspace", json={"action": "member", "tenant": a}
                    )
                ).status_code == 403
                payload = {
                    "action": "checkout",
                    "tenant": a,
                    "request": uid(),
                    "customer": "Test customer",
                    "payment": "cash",
                    "tendered": 25000,
                    "expected": 21240,
                    "discount": 2000,
                    "tax_bps": 1800,
                    "items": [{"id": pid, "quantity": 2}],
                }
                response = await cashier.post("/api/workspace", json=payload)
                assert response.status_code == 200, response.text
                sale = response.json()
                assert sale["total"] == 21240
                again = await cashier.post("/api/workspace", json=payload)
                assert again.json()["id"] == sale["id"]
                bad = await cashier.post(
                    "/api/workspace",
                    json={
                        **payload,
                        "request": uid(),
                        "items": [{"id": pid, "quantity": 6}],
                    },
                )
                assert bad.status_code == 400
                bad = await cashier.post(
                    "/api/workspace",
                    json={
                        "action": "return",
                        "tenant": a,
                        "id": sale["id"],
                        "reason": "No permission",
                    },
                )
                assert bad.status_code == 403
                pdf = await cashier.get(
                    "/api/invoices/" + sale["id"] + ".pdf", params={"tenant": a}
                )
                assert pdf.status_code == 200, (
                    pdf.text[:200] if pdf.status_code != 200 else ""
                )
                assert pdf.content.startswith(b"%PDF")
                blocked_pdf = await cashier.get(
                    "/api/invoices/" + sale["id"] + ".pdf", params={"tenant": other}
                )
                assert blocked_pdf.status_code == 403
            data = (await client.get("/api/workspace", params={"tenant": a})).json()
            assert data["products"][0]["stock"] == 3
            assert len(data["sales"]) == 1
            assert (
                await post("return", a, id=sale["id"], reason="Customer return")
            ).status_code == 200
            assert (
                await post("return", a, id=sale["id"], reason="Retry")
            ).status_code == 200
            data = (await client.get("/api/workspace", params={"tenant": a})).json()
            assert data["products"][0]["stock"] == 5
            assert data["stats"]["revenue"] == 0
            assert (
                await client.get(
                    "/api/products/" + pid + "/barcode.pdf", params={"tenant": a}
                )
            ).content.startswith(b"%PDF")
            movement = {
                "product": pid,
                "type": "OUT",
                "quantity": 1,
                "notes": "Damaged",
                "request": uid(),
            }
            assert (await post("movement", a, **movement)).status_code == 200
            assert (await post("movement", a, **movement)).status_code == 200
            assert (await client.get("/api/workspace", params={"tenant": a})).json()[
                "products"
            ][0]["stock"] == 4
            assert (
                await post(
                    "movement",
                    a,
                    product=pid,
                    type="OUT",
                    quantity=10,
                    notes="Too many",
                    request=uid(),
                )
            ).status_code == 400
            assert (
                await post(
                    "editProduct",
                    a,
                    id=pid,
                    name="Renamed",
                    category="Hardware",
                    barcode="123456789012",
                    price=20000,
                    cost=6000,
                    reorder=2,
                    active=True,
                )
            ).status_code == 200
            receipt = (
                await client.get(
                    "/api/workspace", params={"tenant": a, "receipt": sale["id"]}
                )
            ).json()
            assert receipt["items"][0]["name"] == "Keyboard"
            assert receipt["items"][0]["price"] == 10000
            member = next(m for m in data["members"] if m["email"] == member_email)
            assert (
                await post("memberStatus", a, id=member["id"], active=False)
            ).status_code == 200
            assert (
                await post("tenantStatus", a, status="suspended")
            ).status_code == 200
            assert (
                await client.get("/api/workspace", params={"tenant": a})
            ).status_code == 403
            assert (await post("tenantStatus", a, status="active")).status_code == 200
            csrf = await client.post(
                "/api/workspace",
                json={"action": "tenant"},
                headers={"Origin": "https://evil.example"},
            )
            assert csrf.status_code == 403
            changed = await client.post(
                "/api/auth/password",
                json={
                    "current": config.ADMIN_PASSWORD,
                    "password": "NewTestPassword!2026",
                },
            )
            assert changed.status_code == 200
            # Revert for repeatable test runs; this still validates session renewal.
            assert (
                await client.post(
                    "/api/auth/password",
                    json={
                        "current": "NewTestPassword!2026",
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200
            assert (await client.post("/api/auth/logout")).status_code == 200
            assert (await client.get("/api/workspace")).status_code == 401


@pytest.mark.skipif(
    os.getenv("RUN_CONCURRENCY") != "1",
    reason="Run explicitly against real PostgreSQL with RUN_CONCURRENCY=1",
)
@pytest.mark.asyncio
async def test_concurrent_checkout_cannot_oversell():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.getenv("TEST_DATABASE_URL")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as client:
            assert (
                await client.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200
            t = (
                await client.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Concurrent test",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            assert (
                await client.post(
                    "/api/workspace",
                    json={
                        "action": "product",
                        "tenant": t,
                        "sku": "LAST-ONE",
                        "name": "One item",
                        "category": "Test",
                        "price": 100,
                        "cost": 0,
                        "initial": 1,
                        "reorder": 0,
                        "barcode": "",
                    },
                )
            ).status_code == 200
            p = (await client.get("/api/workspace", params={"tenant": t})).json()[
                "products"
            ][0]["id"]

            async def buy():
                return await client.post(
                    "/api/workspace",
                    json={
                        "action": "checkout",
                        "tenant": t,
                        "request": str(uuid.uuid4()),
                        "items": [{"id": p, "quantity": 1}],
                        "expected": 100,
                        "discount": 0,
                        "tax_bps": 0,
                        "tendered": 100,
                        "payment": "cash",
                        "customer": "Concurrent customer",
                    },
                )

            results = await asyncio.gather(buy(), buy())
            assert sorted(r.status_code for r in results) == [200, 400]
            d = (await client.get("/api/workspace", params={"tenant": t})).json()
            assert d["products"][0]["stock"] == 0
            assert len(d["sales"]) == 1
