"""Over-tender is change, never revenue, khata credit or extra till cash."""

import os
import uuid
import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_cash_change_receipts_retries_split_credit_and_shortfall():
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
            assert (
                await c.post(
                    "/api/auth/login",
                    json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
                )
            ).status_code == 200

            async def old(action, **payload):
                r = await c.post("/api/workspace", json=dict(action=action, **payload))
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Cash change tests", currency="PKR"))[
                "id"
            ]
            base = f"/api/v1/tenants/{tenant}"
            pid = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="CASH",
                    name="Cash item",
                    category="General",
                    price=125050,
                    cost=100000,
                    initial=20,
                    reorder=1,
                )
            )["id"]
            methods = (
                await c.get(base + "/lookups", params={"kind": "payment_method"})
            ).json()["items"]
            cash = next(x["id"] for x in methods if x["code"] == "cash")
            external = next(x["id"] for x in methods if x["code"] != "cash")
            payload = dict(
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=[dict(id=pid, quantity=1)],
                payment="cash",
                expected=125050,
                tendered=200000,
            )
            sale = await old("checkout", **payload)
            assert (
                sale["cash_received"] == 200000
                and sale["cash_amount"] == 125050
                and sale["change"] == 74950
            )
            assert await old("checkout", **payload) == sale

            async def receipt(sid):
                # Public receipt endpoint used by the React UI.
                r = await c.get(
                    "/api/workspace", params=dict(tenant=tenant, receipt=sid)
                )
                assert r.status_code == 200, r.text
                return r.json()

            data = await receipt(sale["id"])
            assert (
                data["sale"]["change"] == 74950 and data["sale"]["paid_now"] == 125050
            )
            for lang in ["en", "ur"]:
                r = await c.get(
                    f"/api/invoices/{sale['id']}.pdf",
                    params=dict(tenant=tenant, language=lang),
                )
                assert r.status_code == 200 and r.content.startswith(b"%PDF"), r.text
            split = {
                **payload,
                "request": uuid.uuid4().hex,
                "tendered": 100000,
                "tenders": [
                    dict(method_id=cash, amount=75050),
                    dict(method_id=external, amount=50000),
                ],
            }
            s = await old("checkout", **split)
            assert s["change"] == 24950 and s["cash_amount"] == 75050
            assert (await receipt(s["id"]))["sale"]["change"] == 24950
            exact = await old(
                "checkout",
                **{**payload, "request": uuid.uuid4().hex, "tendered": 125050},
            )
            assert exact["change"] == 0
            ext = await old(
                "checkout",
                **{
                    **payload,
                    "request": uuid.uuid4().hex,
                    "payment": "external",
                    "tendered": 0,
                },
            )
            assert ext["change"] == 0 and ext["cash_received"] == 0
            short = await c.post(
                "/api/workspace",
                json=dict(
                    action="checkout",
                    **{**payload, "request": uuid.uuid4().hex, "tendered": 125049},
                ),
            )
            assert short.status_code == 400
            async with db.pool.acquire() as conn:
                # Only net cash is counted; failed checkout has no sale/stock effects.
                assert (
                    await conn.fetchval(
                        "SELECT SUM(cash_amount) FROM sales WHERE tenant=$1", tenant
                    )
                    == 325150
                )
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM sales WHERE tenant=$1", tenant
                    )
                    == 4
                )

            person = (
                await c.post(
                    base + "/customers",
                    json=dict(name="Credit customer", phone="03001234567"),
                )
            ).json()["id"]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE customers SET credit_limit=100000,credit_enabled=true WHERE tenant=$1 AND id=$2",
                    tenant,
                    person,
                )
            from datetime import date, timedelta

            khata = await old(
                "checkout",
                **{
                    **payload,
                    "request": uuid.uuid4().hex,
                    "customer_id": person,
                    "paid_now": 50000,
                    "due_date": (date.today() + timedelta(days=2)).isoformat(),
                    "tendered": 100000,
                },
            )
            assert khata["credit_amount"] == 75050 and khata["change"] == 50000
            assert (await receipt(khata["id"]))["sale"]["change"] == 50000
