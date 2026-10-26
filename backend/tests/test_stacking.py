"""Combined offers keep tax, redemptions and frozen return allocations consistent."""

import os
import uuid
from decimal import Decimal
import httpx
import pytest


def test_connected_return_groups():
    from app.features.promotions import return_groups

    assert return_groups({}) == []
    offers = [
        dict(kind="cross_bogo", buy_product="A", reward_product="B"),
        dict(kind="cross_bogo", buy_product="B", reward_product="C"),
        dict(kind="cross_bogo", buy_product="D", reward_product="E"),
    ]
    assert sorted(return_groups({"offers": offers})) == [["A", "B", "C"], ["D", "E"]]


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_combined_offers_tax_caps_replay_returns():
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
                json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )

            async def old(action, **kw):
                r = await c.post("/api/workspace", json=dict(action=action, **kw))
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Stacking QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"

            async def post(path, payload):
                r = await c.post(base + path, json=payload)
                assert r.status_code in (200, 201), r.text
                return r.json()

            a = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="A",
                    name="A",
                    category="General",
                    price=1000,
                    cost=100,
                    initial=30,
                    reorder=0,
                )
            )["id"]
            b = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="B",
                    name="B",
                    category="General",
                    price=2000,
                    cost=200,
                    initial=30,
                    reorder=0,
                )
            )["id"]

            async def promo(code, kind, value=0, **kw):
                return await post(
                    "/promotions",
                    dict(
                        code=code,
                        name=code,
                        kind=kind,
                        value=value,
                        stackable=True,
                        **kw,
                    ),
                )

            fixed = await promo("FIX", "fixed", 100)
            p10 = await promo("P10", "percentage", 1000, usage_limit=1)
            await promo("P20", "percentage", 2000)
            await post(
                "/promotions",
                dict(code="SOLO", name="Single offer", kind="fixed", value=100),
            )
            cart = [dict(id=a, quantity=2), dict(id=b, quantity=1)]
            payload = dict(items=cart, promotion_code="P20,FIX,P10", tax_bps=1000)
            quote = await post("/sales/quote", payload)
            # 4000-100=3900; -10%=3510; -20%=2808; +10% tax=3089.
            assert quote["discount"] == 1192 and quote["total"] == 3089
            assert [o["code"] for o in quote["promotion"]["offers"]] == [
                "FIX",
                "P10",
                "P20",
            ]
            assert sum(o["discount"] for o in quote["promotion"]["offers"]) == 1192
            reordered = await post(
                "/sales/quote", {**payload, "promotion_code": "FIX, P10, P20"}
            )
            assert reordered["quote_token"] == quote["quote_token"]
            for code in (
                "FIX,FIX",
                "FIX,",
                "FIX,SOLO",
                "FIX,NOTFOUND",
                "FIX,P10,P20,SOLO,OTHER,SIXTH",
            ):
                r = await c.post(
                    base + "/sales/quote", json={**payload, "promotion_code": code}
                )
                assert r.status_code in (400, 404, 409), r.text
            assert (
                await c.post(base + "/sales/quote", json={**payload, "discount": 1})
            ).status_code == 400
            assert (
                await c.post(
                    base + "/sales/quote", json={**payload, "auto_promotion": True}
                )
            ).status_code == 400
            held = await post(
                "/held-bills",
                dict(
                    id=uuid.uuid4().hex,
                    label="Stack",
                    items=cart,
                    promotion_code=payload["promotion_code"],
                ),
            )
            held_items = (await c.get(base + "/held-bills")).json()["items"]
            assert (
                held_items[0]["payload"]["promotion_code"] == payload["promotion_code"]
            )
            sale_payload = dict(
                **payload,
                request=uuid.uuid4().hex,
                payment="cash",
                expected=quote["total"],
                tendered=4000,
                quote_token=quote["quote_token"],
            )
            # Insufficient payment does not spend any of the capped offer's uses.
            assert (
                await c.post(base + "/sales", json={**sale_payload, "tendered": 1})
            ).status_code == 400
            sale = await post("/sales", sale_payload)
            assert await post("/sales", sale_payload) == sale
            async with db.pool.acquire() as conn:
                redemptions = await conn.fetch(
                    "SELECT * FROM promotion_redemptions WHERE tenant=$1 AND sale=$2",
                    tenant,
                    sale["id"],
                )
                assert (
                    len(redemptions) == 3
                    and sum(r["discount"] for r in redemptions) == 1192
                )
            assert (
                await c.post(base + "/sales/quote", json=payload)
            ).status_code == 409
            receipt = (await c.get(base + f"/sales/{sale['id']}")).json()
            snapshot = receipt["sale"]["promotion_snapshot"]
            snapshot = (
                __import__("json").loads(snapshot)
                if isinstance(snapshot, str)
                else snapshot
            )
            assert len(snapshot["offers"]) == 3
            for language in ("en", "ur"):
                pdf = await c.get(
                    f"/api/invoices/{sale['id']}.pdf",
                    params={"tenant": tenant, "language": language},
                )
                assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            # Cross BOGO + percentage: reward line remains zero; return pairing is frozen.
            cross = await promo(
                "PAIR",
                "cross_bogo",
                reward_product=b,
                components=[dict(product=a, quantity=1), dict(product=b, quantity=1)],
            )
            cross_body = dict(
                items=[dict(id=a, quantity=1), dict(id=b, quantity=1)],
                promotion_code="P20,PAIR",
            )
            q = await post("/sales/quote", cross_body)
            assert q["discount"] == 2200 and q["total"] == 800
            assert {
                x["product"]: x["discount"] for x in q["promotion"]["line_discounts"]
            } == {a: 200, b: 2000}
            cross_sale = await post(
                "/sales",
                dict(
                    **cross_body,
                    request=uuid.uuid4().hex,
                    payment="cash",
                    expected=800,
                    tendered=800,
                    quote_token=q["quote_token"],
                ),
            )
            rec = (await c.get(base + f"/sales/{cross_sale['id']}")).json()
            assert set(rec["sale"]["return_pair_products"]) == {a, b}
            url = f"/sales/{cross_sale['id']}/adjustments"
            one = dict(
                revision=0,
                returns=[
                    dict(item=rec["items"][0]["id"], quantity=1, reason="damaged")
                ],
            )
            assert (await c.post(base + url + "/preview", json=one)).status_code == 409
            both = dict(
                revision=0,
                returns=[
                    dict(item=i["id"], quantity=1, reason="damaged")
                    for i in rec["items"]
                ],
            )
            q = await post(url + "/preview", both)
            assert q["credit"] == 800
            await post(
                url,
                dict(
                    **both,
                    request=uuid.uuid4().hex,
                    quote_token=q["quote_token"],
                    settlement="external",
                    reference="Recorded refund",
                ),
            )
            original = (await c.get(base + url + "/original")).json()
            assert set(original["sale"]["return_pair_products"]) == {a, b}
            # Multiple product offers cap each line, never move a reward to other products.
            await promo("BOGO", "bogo", components=[dict(product=a, quantity=1)])
            await promo(
                "BUNDLE",
                "bundle",
                1500,
                components=[dict(product=a, quantity=1), dict(product=b, quantity=1)],
            )
            q = await post(
                "/sales/quote", dict(items=cart, promotion_code="BOGO,BUNDLE,P20")
            )
            assert all(
                0 <= x["discount"] <= ({a: 2000, b: 2000}[x["product"]])
                for x in q["promotion"]["line_discounts"]
            )
            assert (
                sum(x["discount"] for x in q["promotion"]["line_discounts"])
                == q["discount"]
            )
            await promo("FREE", "percentage", 10000)
            assert (
                await c.post(
                    base + "/sales/quote",
                    json=dict(items=cart, promotion_code="FREE,P20"),
                )
            ).status_code == 409
            # Customer caps still apply separately to every combined offer.
            limited = await promo("PERSON", "fixed", 50, per_customer_limit=1)
            limited_body = dict(items=cart, promotion_code="PERSON,FIX")
            assert (
                await c.post(base + "/sales/quote", json=limited_body)
            ).status_code == 400
            customer = await post(
                "/customers", dict(name="Registered", phone="03000000000")
            )
            limited_body["customer_id"] = customer["id"]
            q = await post("/sales/quote", limited_body)
            await post(
                "/sales",
                dict(
                    **limited_body,
                    request=uuid.uuid4().hex,
                    payment="cash",
                    expected=q["total"],
                    tendered=4000,
                    quote_token=q["quote_token"],
                ),
            )
            assert (
                await c.post(base + "/sales/quote", json=limited_body)
            ).status_code == 409
            # Changing stackability/version after preview invalidates checkout.
            q = await post("/sales/quote", dict(items=cart, promotion_code="FIX,P20"))
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE promotions SET stackable=false,version=version+1 WHERE id=$1",
                    fixed["id"],
                )
            denied = await c.post(
                base + "/sales",
                json=dict(
                    items=cart,
                    promotion_code="FIX,P20",
                    request=uuid.uuid4().hex,
                    payment="cash",
                    expected=q["total"],
                    tendered=4000,
                    quote_token=q["quote_token"],
                ),
            )
            assert denied.status_code == 409, denied.text
