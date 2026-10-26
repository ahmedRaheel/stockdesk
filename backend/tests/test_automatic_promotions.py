import os
import uuid
import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_automatic_selection_tax_caps_quotes_returns_and_hold():
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
            second = (
                await post(
                    "product",
                    t,
                    sku="MILK",
                    name="Milk",
                    category="General",
                    price=1100,
                    cost=500,
                    initial=50,
                    reorder=0,
                )
            )["id"]
            tax = await c.post(
                base + "/tax-profiles",
                json=dict(name="Taxed", rate_bps=10000, inclusive=False),
            )
            assert tax.status_code == 201, tax.text
            assert (
                await c.put(
                    base + "/products/" + product,
                    json=dict(
                        name="Tea",
                        category="General",
                        price=1000,
                        cost=500,
                        reorder=0,
                        tax_profile_id=tax.json()["id"],
                    ),
                )
            ).status_code == 200
            assert (
                await c.put(base + "/tax-settings", json=dict(mode="configured"))
            ).status_code == 200

            async def offer(code, **kw):
                body = dict(
                    code=code, name=code, kind="fixed", value=200, automatic=True, **kw
                )
                r = await c.post(base + "/promotions", json=body)
                assert r.status_code == 201, r.text
                return r.json()["id"], body

            async def create(body):
                r = await c.post(base + "/promotions", json=body)
                assert r.status_code == 201, r.text
                return r.json()["id"]

            pa = await create(
                dict(
                    code="TAX",
                    name="Taxed BOGO",
                    kind="bogo",
                    automatic=True,
                    usage_limit=1,
                    components=[dict(product=product, quantity=1)],
                )
            )
            pb = await create(
                dict(
                    code="LARGER",
                    name="Larger pretax discount",
                    kind="bogo",
                    automatic=True,
                    usage_limit=1,
                    components=[dict(product=second, quantity=1)],
                )
            )
            await create(
                dict(code="MANUAL", name="Not automatic", kind="fixed", value=4000)
            )
            await create(
                dict(
                    code="INACTIVE",
                    name="Inactive",
                    kind="fixed",
                    value=4000,
                    automatic=True,
                    active=False,
                )
            )
            await create(
                dict(
                    code="FUTURE",
                    name="Future",
                    kind="fixed",
                    value=4000,
                    automatic=True,
                    starts_on="2099-01-01",
                )
            )
            await create(
                dict(
                    code="MINIMUM",
                    name="Minimum",
                    kind="fixed",
                    value=4000,
                    automatic=True,
                    minimum_subtotal=100000,
                )
            )
            cart = [dict(id=product, quantity=2), dict(id=second, quantity=2)]

            async def quote(**kw):
                return await c.post(
                    base + "/sales/quote",
                    json=dict(items=cart, auto_promotion=True, **kw),
                )

            q = (await quote()).json()
            assert (
                q["promotion"]["id"] == pa
                and q["discount"] == 1000
                and q["total"] == 4200
            ), q
            assert q["promotion"]["automatic"] is True
            assert (await quote(discount=1)).status_code == 400
            assert (await quote(promotion_code="MANUAL")).status_code == 400
            payload = dict(
                items=cart,
                auto_promotion=True,
                quote_token=q["quote_token"],
                request=uuid.uuid4().hex,
                payment="cash",
                expected=q["total"],
                tendered=q["total"],
            )
            assert (
                await c.post(base + "/sales", json={**payload, "expected": 1})
            ).status_code == 400
            sold = await c.post(base + "/sales", json=payload)
            assert sold.status_code == 200, sold.text
            assert (await c.post(base + "/sales", json=payload)).json()[
                "id"
            ] == sold.json()["id"]
            next_quote = (await quote()).json()
            assert (
                next_quote["promotion"]["id"] == pb and next_quote["total"] == 5100
            ), next_quote
            assert (
                await c.post(
                    base + "/sales", json={**payload, "request": uuid.uuid4().hex}
                )
            ).status_code == 409
            await post(
                "return", t, id=sold.json()["id"], reason="Return automatic sale"
            )
            assert (await quote()).json()["promotion"]["id"] == pb
            sold = await c.post(
                base + "/sales",
                json={
                    **payload,
                    "request": uuid.uuid4().hex,
                    "quote_token": next_quote["quote_token"],
                    "expected": 5100,
                    "tendered": 5100,
                },
            )
            assert sold.status_code == 200, sold.text
            none = (await quote()).json()
            assert (
                none["total"] == 6200
                and "promotion" not in none
                and none["auto_promotion"] is True
            )
            # Equal final totals break ties by code, independent of insertion order.
            await offer("BBB")
            winner, body = await offer("AAA")
            assert (await quote()).json()["promotion"]["id"] == winner
            person_offer = await create(
                dict(
                    code="PERSON",
                    name="Customer reward",
                    kind="fixed",
                    value=3000,
                    automatic=True,
                    per_customer_limit=1,
                )
            )
            assert (await quote()).json()["promotion"]["id"] == winner
            personal = (await quote(customer_id=a)).json()
            assert personal["promotion"]["id"] == person_offer
            person_payload = {
                **payload,
                "request": uuid.uuid4().hex,
                "customer_id": a,
                "quote_token": personal["quote_token"],
                "expected": personal["total"],
                "tendered": personal["total"],
            }
            sold = await c.post(base + "/sales", json=person_payload)
            assert sold.status_code == 200, sold.text
            assert (await quote(customer_id=a)).json()["promotion"]["id"] == winner
            assert (await quote(customer_id=b)).json()["promotion"][
                "id"
            ] == person_offer
            held = dict(
                id=uuid.uuid4().hex,
                label="Automatic bill",
                items=cart,
                customer_id=b,
                auto_promotion=True,
            )
            assert (await c.post(base + "/held-bills", json=held)).status_code == 200
            assert (await c.post(base + "/held-bills", json=held)).status_code == 200
            assert (await c.get(base + "/held-bills")).json()["items"][0]["payload"][
                "auto_promotion"
            ] is True
            # Bound evaluation work rather than silently omitting eligible offers.
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE promotions SET automatic=false WHERE tenant=$1", t
                )
                await conn.execute(
                    "INSERT INTO promotions(id,tenant,code,name,kind,value,automatic) SELECT 'limit-'||$1||i::text,$1,'LIMIT'||i::text,'Limit','fixed',1,true FROM generate_series(1,100) i",
                    t,
                )
            capped = await c.post(
                base + "/promotions", json=body | dict(code="OVER", name="Over limit")
            )
            assert capped.status_code == 400, capped.text
