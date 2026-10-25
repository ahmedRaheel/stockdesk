import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.api.promotions import Promotion
from app.features.promotions import evaluate


def campaign(**changes):
    return Promotion(
        **{
            **dict(
                code="CROSS",
                name="Buy A get B",
                kind="cross_bogo",
                buy_quantity=2,
                free_quantity=1,
                reward_product="reward",
                components=[
                    dict(product="reward", quantity=1),
                    dict(product="buy", quantity=1),
                ],
            ),
            **changes,
        }
    )


def test_cross_bogo_reward_allocation_repetition_caps_and_contracts():
    offer = campaign()
    rule = {**offer.model_dump(), "id": "offer", "version": 1}
    items = [
        dict(id="buy", quantity=Decimal(5), price=100, line_total=500),
        dict(id="reward", quantity=Decimal(4), price=200, line_total=800),
        dict(id="other", quantity=Decimal(1), price=300, line_total=300),
    ]
    now = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
    parts = [c.model_dump() for c in offer.components]
    result = evaluate(rule, parts, items, now)
    assert result["discount"] == 400 and result["reward_units"] == 2
    assert result["buy_product"] == "buy" and result["reward_product"] == "reward"
    assert [x["discount"] for x in result["line_discounts"]] == [0, 400, 0]
    from app.features.taxation import calculate

    taxed = calculate(
        [
            {**items[0], "rate_bps": 1000, "inclusive": False},
            {**items[1], "rate_bps": 2000, "inclusive": True},
            {**items[2], "rate_bps": 0, "inclusive": False},
        ],
        400,
        "configured",
        line_discounts=[0, 400, 0],
    )
    assert (
        taxed["tax"] == 117 and taxed["tax_included"] == 67 and taxed["total"] == 1250
    )
    reverse = evaluate(rule, list(reversed(parts)), list(reversed(items)), now)
    assert (
        reverse["discount"] == 400 and reverse["line_discounts"][1]["discount"] == 400
    )
    assert (
        evaluate({**rule, "maximum_discount": 175}, parts, items, now)["discount"]
        == 175
    )
    one = [items[0], {**items[1], "quantity": Decimal(1), "line_total": 200}]
    assert evaluate(rule, parts, one, now)["discount"] == 200
    for cart in [
        items[:1],
        items[1:],
        [{**items[0], "quantity": Decimal(1), "line_total": 100}, items[1]],
        [{**items[0], "quantity": Decimal("2.5")}, items[1]],
    ]:
        with pytest.raises(HTTPException):
            evaluate(rule, parts, cart, now)
    for change in [
        dict(reward_product=None),
        dict(reward_product="missing"),
        dict(value=1),
        dict(components=[dict(product="buy", quantity=1)]),
        dict(
            components=[
                dict(product="buy", quantity=1),
                dict(product="buy", quantity=1),
            ]
        ),
        dict(
            components=[
                dict(product="buy", quantity=2),
                dict(product="reward", quantity=1),
            ]
        ),
    ]:
        with pytest.raises(ValidationError):
            campaign(**change)
    with pytest.raises(ValidationError):
        Promotion(
            code="FIXED",
            name="Invalid",
            kind="fixed",
            value=100,
            reward_product="reward",
        )


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_cross_bogo_checkout_tax_frozen_returns_and_stock():
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

            tenant = (await old("tenant", name="Cross BOGO QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"
            ids = []
            for sku, price in [("BUY", 1000), ("GIFT", 1500), ("OTHER", 500)]:
                ids.append(
                    (
                        await old(
                            "product",
                            tenant=tenant,
                            sku=sku,
                            name=sku,
                            category="General",
                            price=price,
                            cost=300,
                            initial=20,
                            reorder=1,
                        )
                    )["id"]
                )
            buy, reward, other = ids
            # Configure through the same tables as production; tax API CRUD is covered separately.
            async with db.pool.acquire() as conn:
                taxid = uuid.uuid4().hex
                await conn.execute(
                    "INSERT INTO tax_profiles(id,tenant,name,rate_bps,inclusive) VALUES($1,$2,'Cross VAT',1000,false)",
                    taxid,
                    tenant,
                )
                await conn.execute(
                    "UPDATE tenants SET tax_mode='configured',default_tax_profile=$1 WHERE id=$2",
                    taxid,
                    tenant,
                )
            offer = dict(
                code="CROSS",
                name="Buy two, get gift",
                kind="cross_bogo",
                buy_quantity=2,
                free_quantity=1,
                reward_product=reward,
                components=[
                    dict(product=reward, quantity=1),
                    dict(product=buy, quantity=1),
                ],
            )
            created = await c.post(base + "/promotions", json=offer)
            assert created.status_code == 201, created.text
            pid = created.json()["id"]
            assert (await c.get(base + "/promotions?q=CROSS")).json()["items"][0][
                "reward_product"
            ] == reward
            cart = [
                dict(id=buy, quantity=4),
                dict(id=reward, quantity=3),
                dict(id=other, quantity=2),
            ]
            quoted = await c.post(
                base + "/sales/quote", json=dict(items=cart, promotion_code="CROSS")
            )
            assert quoted.status_code == 200, quoted.text
            quote = quoted.json()
            assert (
                quote["discount"] == 3000
                and quote["tax"] == 650
                and quote["total"] == 7150
            )
            assert (
                next(x for x in quote["lines"] if x["product"] == reward)["discount"]
                == 3000
            )
            assert (
                next(x for x in quote["lines"] if x["product"] == buy)["discount"] == 0
            )
            payload = dict(
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=cart,
                payment="cash",
                expected=7150,
                tendered=8000,
                promotion_code="CROSS",
                quote_token=quote["quote_token"],
            )
            sale = await old("checkout", **payload)
            receipt = (await c.get(base + f"/sales/{sale['id']}")).json()
            assert set(receipt["sale"]["return_pair_products"]) == {buy, reward}
            for language in ["en", "ur"]:
                pdf = await c.get(
                    f"/api/invoices/{sale['id']}.pdf",
                    params=dict(tenant=tenant, language=language),
                )
                assert pdf.status_code == 200 and pdf.content.startswith(
                    b"%PDF"
                ), pdf.text
            item_ids = {i["product"]: i["id"] for i in receipt["items"]}
            url = base + f"/sales/{sale['id']}/adjustments"

            def line(product, qty):
                return dict(
                    item=item_ids[product],
                    quantity=qty,
                    reason="incorrect",
                    restock=True,
                )

            for lines in [
                [line(buy, 4)],
                [line(reward, 3)],
                [line(buy, 2), line(reward, 1)],
            ]:
                rejected = await c.post(
                    url + "/preview", json=dict(revision=0, returns=lines)
                )
                assert rejected.status_code == 409 and "together" in rejected.text

            # An unrelated item remains independently returnable.
            async def commit(revision, returns):
                body = dict(revision=revision, returns=returns)
                r = await c.post(url + "/preview", json=body)
                assert r.status_code == 200, r.text
                request = {
                    **body,
                    "request": uuid.uuid4().hex,
                    "quote_token": r.json()["quote_token"],
                    "settlement": "external",
                    "reference": "Recorded refund",
                }
                posted = await c.post(url, json=request)
                assert posted.status_code == 200, posted.text
                assert (await c.post(url, json=request)).json() == posted.json()
                return posted.json()

            unrelated = await commit(0, [line(other, 1)])
            assert unrelated["credit"] == 550
            # Changing the live offer must not change historical return protection or values.
            changed = {
                **offer,
                "reward_product": other,
                "components": [
                    dict(product=buy, quantity=1),
                    dict(product=other, quantity=1),
                ],
                "version": 1,
            }
            assert (
                await c.put(base + f"/promotions/{pid}", json=changed)
            ).status_code == 200
            revised = (await c.get(base + f"/sales/{sale['id']}")).json()
            assert set(revised["sale"]["return_pair_products"]) == {buy, reward}
            assert (
                await c.post(
                    url + "/preview", json=dict(revision=1, returns=[line(buy, 4)])
                )
            ).status_code == 409
            pair = await commit(1, [line(buy, 4), line(reward, 3)])
            assert pair["credit"] == 6050
            revised = (await c.get(base + f"/sales/{sale['id']}")).json()
            assert (
                revised["sale"]["return_pair_products"] == []
                and revised["sale"]["total"] == 550
            )
            final = await commit(2, [line(other, 1)])
            assert final["credit"] == 550
            assert await old("checkout", **payload) == sale
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM promotion_redemptions WHERE tenant=$1 AND promotion=$2",
                        tenant,
                        pid,
                    )
                    == 1
                )
                for product in ids:
                    assert (
                        await conn.fetchval(
                            "SELECT stock FROM products WHERE id=$1", product
                        )
                        == 20
                    )
            # Cannot use foreign reward products or fractional-unit components.
            other_tenant = (await old("tenant", name="Foreign gift", currency="PKR"))[
                "id"
            ]
            foreign = (
                await old(
                    "product",
                    tenant=other_tenant,
                    sku="FOREIGN",
                    name="Foreign",
                    category="General",
                    price=100,
                    cost=1,
                    initial=1,
                    reorder=0,
                )
            )["id"]
            bad = {
                **offer,
                "code": "FOREIGN",
                "reward_product": foreign,
                "components": [
                    dict(product=buy, quantity=1),
                    dict(product=foreign, quantity=1),
                ],
            }
            assert (await c.post(base + "/promotions", json=bad)).status_code == 400
            units = (await c.get(base + "/lookups?kind=unit")).json()["items"]
            kg = next(x["id"] for x in units if x["code"] == "kg")
            weighted = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="WEIGHT",
                    name="Weighted",
                    category="General",
                    unit_id=kg,
                    price=100,
                    cost=1,
                    initial=1,
                    reorder=0,
                )
            )["id"]
            bad = {
                **offer,
                "code": "WEIGHT",
                "reward_product": weighted,
                "components": [
                    dict(product=buy, quantity=1),
                    dict(product=weighted, quantity=1),
                ],
            }
            assert (await c.post(base + "/promotions", json=bad)).status_code == 400

            # An inactive component must not prevent disabling an existing offer.
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE products SET active=false WHERE id=$1", buy)
            disabled = await c.put(
                base + f"/promotions/{pid}",
                json={**changed, "version": 2, "active": False},
            )
            assert disabled.status_code == 200, disabled.text
            assert (
                await c.put(
                    base + f"/promotions/{pid}",
                    json={**changed, "version": 3, "active": True},
                )
            ).status_code == 400
