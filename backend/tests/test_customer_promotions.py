import json
import os
import uuid
import httpx
import pytest
from pydantic import ValidationError
from app.api.promotions import Promotion


def test_customer_limit_contract():
    data = dict(code="ONE", name="Offer", kind="fixed", value=100)
    assert Promotion(**data).per_customer_limit is None
    for value in [0, -1, 1.5, True, "1", 1000000001]:
        with pytest.raises(ValidationError):
            Promotion(**data, per_customer_limit=value)
    assert Promotion(**data, per_customer_limit=1).per_customer_limit == 1


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_customer_limit_quote_checkout_history_and_tenant_boundaries():
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

            async def post(action, tenant="", **kw):
                r = await c.post(
                    "/api/workspace", json=dict(action=action, tenant=tenant, **kw)
                )
                assert r.status_code == 200, r.text
                return r.json()

            t = (await post("tenant", name="Customer offers", currency="PKR"))["id"]
            other = (await post("tenant", name="Other customers", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}"
            product = (
                await post(
                    "product",
                    t,
                    sku="TEA",
                    name="Tea",
                    category="General",
                    price=1000,
                    cost=500,
                    initial=50,
                    reorder=0,
                )
            )["id"]

            async def person(name, tenant=t):
                r = await c.post(
                    f"/api/v1/tenants/{tenant}/customers", json=dict(name=name)
                )
                assert r.status_code == 201, r.text
                return r.json()["id"]

            a, b = await person("Customer A"), await person("Customer B")
            foreign = await person("Foreign", other)
            inactive = await person("Inactive")
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE customers SET active=false WHERE tenant=$1 AND id=$2",
                    t,
                    inactive,
                )
            picker = (await c.get(base + "/sale-customers")).json()["items"]
            assert {x["id"] for x in picker} == {a, b}
            assert all(set(x) == {"id", "name", "phone"} for x in picker)
            for ident in [foreign, inactive]:
                assert (
                    await c.get(base + "/sale-customers/" + ident)
                ).status_code == 404
            offer = dict(
                code="ONCE",
                name="Once per customer",
                kind="fixed",
                value=100,
                per_customer_limit=1,
            )
            r = await c.post(base + "/promotions", json=offer)
            assert r.status_code == 201, r.text
            pid = r.json()["id"]
            assert (await c.get(base + "/promotions")).json()["items"][0][
                "per_customer_limit"
            ] == 1

            async def quote(customer=None):
                return await c.post(
                    base + "/sales/quote",
                    json=dict(
                        items=[dict(id=product, quantity=1)],
                        promotion_code="ONCE",
                        customer_id=customer,
                    ),
                )

            for customer in [None, foreign, inactive]:
                assert (await quote(customer)).status_code == 400
            qa, qb = (await quote(a)).json(), (await quote(b)).json()
            assert qa["total"] == 900 and qa["quote_token"] != qb["quote_token"]
            payload = dict(
                request=uuid.uuid4().hex,
                items=[dict(id=product, quantity=1)],
                promotion_code="ONCE",
                customer_id=a,
                quote_token=qa["quote_token"],
                payment="cash",
                expected=900,
                tendered=1000,
            )
            assert (
                await c.post(base + "/sales", json={**payload, "customer_id": b})
            ).status_code == 409
            assert (
                await c.post(base + "/sales", json={**payload, "expected": 1})
            ).status_code == 400
            assert (await quote(a)).status_code == 200
            sold = await c.post(base + "/sales", json=payload)
            assert sold.status_code == 200, sold.text
            sid = sold.json()["id"]
            assert (await c.post(base + "/sales", json=payload)).json()["id"] == sid
            assert (await quote(a)).status_code == 409
            assert (
                await c.post(
                    base + "/sales", json={**payload, "request": uuid.uuid4().hex}
                )
            ).status_code == 409
            assert (await quote(b)).status_code == 200
            receipt = (await c.get(base + "/sales/" + sid)).json()
            assert (
                json.loads(receipt["sale"]["promotion_snapshot"])["per_customer_limit"]
                == 1
            )
            await post("return", t, id=sid, reason="Customer return")
            assert (await quote(a)).status_code == 409
            offer["per_customer_limit"] = 2
            assert (
                await c.put(base + "/promotions/" + pid, json={**offer, "version": 1})
            ).status_code == 200
            q = (await quote(a)).json()
            result = await c.post(
                base + "/sales",
                json={
                    **payload,
                    "request": uuid.uuid4().hex,
                    "quote_token": q["quote_token"],
                },
            )
            assert result.status_code == 200, result.text
            assert (
                await c.put(
                    base + "/promotions/" + pid,
                    json={**offer, "per_customer_limit": 1, "version": 2},
                )
            ).status_code == 400
            assert (
                await c.put(
                    base + "/promotions/" + pid,
                    json={**offer, "per_customer_limit": None, "version": 2},
                )
            ).status_code == 200
            q = (await quote(a)).json()
            result = await c.post(
                base + "/sales",
                json={
                    **payload,
                    "request": uuid.uuid4().hex,
                    "quote_token": q["quote_token"],
                },
            )
            assert result.status_code == 200, result.text
            assert (
                await c.put(base + "/promotions/" + pid, json={**offer, "version": 3})
            ).status_code == 400
            assert (await quote()).status_code == 200
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2 AND customer=$3",
                        t,
                        pid,
                        a,
                    )
                    == 3
                )
            assert (
                await c.put(
                    base + "/promotions/" + pid,
                    json={
                        **offer,
                        "per_customer_limit": 3,
                        "usage_limit": 3,
                        "version": 3,
                    },
                )
            ).status_code == 200
            assert (await quote(b)).status_code == 409
