from datetime import datetime, date, timezone
from decimal import Decimal
import os
import uuid
import pytest
import httpx
from fastapi import HTTPException
from app.features.promotions import evaluate
from app.features.taxation import calculate


def rule(**kw):
    return (
        dict(
            id="p",
            code="OFFER",
            name="Offer",
            name_ur="",
            kind="percentage",
            value=1000,
            minimum_subtotal=0,
            maximum_discount=None,
            buy_quantity=1,
            free_quantity=1,
            starts_on=None,
            ends_on=None,
            starts_minute=None,
            ends_minute=None,
            usage_limit=None,
            active=True,
            version=1,
            **kw,
        )
        if not kw
        else {**rule(), **kw}
    )


def products():
    return [
        dict(id="a", price=1180, quantity=Decimal(2), line_total=2360),
        dict(id="b", price=1000, quantity=Decimal(1), line_total=1000),
    ]


NOW = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)  # 15:00 Karachi


def test_promotion_percentage_fixed_caps_and_rounding():
    assert evaluate(rule(), [], products(), NOW)["discount"] == 336
    assert (
        evaluate(rule(value=1000, maximum_discount=100), [], products(), NOW)[
            "discount"
        ]
        == 100
    )
    assert (
        evaluate(rule(kind="fixed", value=9999), [], products(), NOW)["discount"]
        == 3360
    )
    assert (
        evaluate(
            rule(value=5000),
            [],
            [dict(id="a", price=1, quantity=Decimal(1), line_total=1)],
            NOW,
        )["discount"]
        == 1
    )
    with pytest.raises(HTTPException):
        evaluate(rule(minimum_subtotal=4000), [], products(), NOW)


def test_bogo_only_discounts_matching_product_and_inclusive_tax():
    p = evaluate(
        rule(kind="bogo", value=0), [dict(product="a", quantity=1)], products(), NOW
    )
    assert p["discount"] == 1180
    assert p["line_discounts"] == [
        dict(product="a", discount=1180),
        dict(product="b", discount=0),
    ]
    lines = [
        {**products()[0], "rate_bps": 1800, "inclusive": True},
        {**products()[1], "rate_bps": 1000, "inclusive": False},
    ]
    q = calculate(lines, p["discount"], "configured", line_discounts=[1180, 0])
    assert q["tax"] == 280 and q["tax_included"] == 180 and q["total"] == 2280
    assert q["lines"][0]["taxable"] == 1000 and q["lines"][1]["taxable"] == 1000
    with pytest.raises(HTTPException):
        evaluate(
            rule(kind="bogo", value=0, buy_quantity=2),
            [dict(product="a", quantity=1)],
            products(),
            NOW,
        )


def test_bundle_repeated_sets_leftovers_and_weighted_components():
    rows = [
        dict(id="a", price=1000, quantity=Decimal(5), line_total=5000),
        dict(id="b", price=2000, quantity=Decimal(2), line_total=4000),
    ]
    r = evaluate(
        rule(kind="bundle", value=3500),
        [
            dict(product="a", quantity=Decimal(2)),
            dict(product="b", quantity=Decimal(1)),
        ],
        rows,
        NOW,
    )
    assert r["discount"] == 1000 and [x["discount"] for x in r["line_discounts"]] == [
        500,
        500,
    ]
    r = evaluate(
        rule(kind="bundle", value=500),
        [
            dict(product="a", quantity=Decimal(".5")),
            dict(product="b", quantity=Decimal(".25")),
        ],
        rows,
        NOW,
    )
    assert r["discount"] == 4000
    with pytest.raises(HTTPException):
        evaluate(
            rule(kind="bundle", value=99999),
            [dict(product="a", quantity=1), dict(product="b", quantity=1)],
            rows,
            NOW,
        )
    with pytest.raises(HTTPException):
        evaluate(
            rule(kind="bundle", value=500),
            [dict(product="a", quantity=1), dict(product="missing", quantity=1)],
            rows,
            NOW,
        )


def test_campaign_dates_and_daily_boundary_and_usage():
    r = rule(
        starts_on=date(2026, 10, 25),
        ends_on=date(2026, 10, 25),
        starts_minute=900,
        ends_minute=901,
        usage_limit=2,
    )
    assert evaluate(r, [], products(), NOW, used=1)["discount"] == 336
    for change in [
        dict(active=False),
        dict(ends_on=date(2026, 10, 24)),
        dict(starts_on=date(2026, 10, 26)),
        dict(ends_minute=900),
        dict(starts_minute=901),
    ]:
        with pytest.raises(HTTPException):
            evaluate({**r, **change}, [], products(), NOW)
    with pytest.raises(HTTPException):
        evaluate(r, [], products(), NOW, used=2)


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_promotion_api_checkout_caps_freeze_permissions_and_retries():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
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

            t = (await post("tenant", name="Promotions", currency="PKR"))["id"]
            other = (await post("tenant", name="Other promos", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}"
            a = (
                await post(
                    "product",
                    t,
                    sku="A",
                    name="Tea",
                    category="General",
                    price=1180,
                    cost=500,
                    initial=20,
                    reorder=1,
                )
            )["id"]
            b = (
                await post(
                    "product",
                    t,
                    sku="B",
                    name="Milk",
                    category="General",
                    price=1000,
                    cost=500,
                    initial=20,
                    reorder=1,
                )
            )["id"]
            foreign = (
                await post(
                    "product",
                    other,
                    sku="X",
                    name="Other",
                    category="General",
                    price=1000,
                    cost=500,
                    initial=2,
                    reorder=0,
                )
            )["id"]
            offer = dict(
                code="SAVE10",
                name="Ten percent",
                kind="percentage",
                value=1000,
                usage_limit=1,
            )
            created = await c.post(base + "/promotions", json=offer)
            assert created.status_code == 201, created.text
            pid = created.json()["id"]
            assert (await c.post(base + "/promotions", json=offer)).status_code == 409
            assert (await c.get(base + "/promotions?q=save")).json()["total"] == 1
            assert (
                await c.post(
                    base + "/promotions",
                    json=dict(
                        code="BAD",
                        name="Bad",
                        kind="bogo",
                        components=[dict(product=foreign, quantity=1)],
                    ),
                )
            ).status_code == 400
            assert (
                await c.post(
                    base + "/promotions",
                    json=dict(
                        code="BAD",
                        name="Bad",
                        kind="bundle",
                        value=1,
                        components=[
                            dict(product=a, quantity=1),
                            dict(product=a, quantity=1),
                        ],
                    ),
                )
            ).status_code == 422
            assert (
                await c.post(
                    base + "/promotions",
                    json={**offer, "code": "DATE", "starts_minute": 900},
                )
            ).status_code == 422
            scheduled = {
                **offer,
                "code": "SUNDAY-NIGHT",
                "weekdays": [6],
                "starts_minute": 1320,
                "ends_minute": 120,
            }
            schedule = await c.post(base + "/promotions", json=scheduled)
            assert schedule.status_code == 201, schedule.text
            saved = (await c.get(base + "/promotions?q=SUNDAY-NIGHT")).json()["items"][
                0
            ]
            assert (
                saved["weekdays"] == [6]
                and saved["starts_minute"] == 1320
                and saved["ends_minute"] == 120
            )
            revised = await c.put(
                base + "/promotions/" + saved["id"],
                json={**scheduled, "version": 1, "weekdays": [4, 5]},
            )
            assert revised.status_code == 200, revised.text
            assert (await c.get(base + "/promotions?q=SUNDAY-NIGHT")).json()["items"][
                0
            ]["weekdays"] == [4, 5]
            cart = [dict(id=a, quantity=2), dict(id=b, quantity=1)]

            async def quote(code, discount=0):
                return await c.post(
                    base + "/sales/quote",
                    json=dict(items=cart, promotion_code=code, discount=discount),
                )

            q = (await quote("save10")).json()
            assert q["discount"] == 336 and q["total"] == 3024
            assert (await quote("SAVE10", 1)).status_code == 400
            # Changing a rule invalidates an existing quote even in manual tax mode.
            offer["name"] = "Updated name"
            assert (
                await c.put(base + "/promotions/" + pid, json={**offer, "version": 1})
            ).status_code == 200
            assert (
                await c.put(base + "/promotions/" + pid, json={**offer, "version": 1})
            ).status_code == 409
            payload = dict(
                request=uuid.uuid4().hex,
                items=cart,
                promotion_code="SAVE10",
                quote_token=q["quote_token"],
                payment="cash",
                expected=q["total"],
                tendered=q["total"],
            )
            assert (await c.post(base + "/sales", json=payload)).status_code == 409
            q = (await quote("SAVE10")).json()
            payload["quote_token"] = q["quote_token"]
            # Failure must not consume a usage or any stock.
            assert (
                await c.post(base + "/sales", json={**payload, "expected": 1})
            ).status_code == 400
            assert (await c.get(base + "/promotions")).json()["items"][0]["used"] == 0
            sale = await c.post(base + "/sales", json=payload)
            assert sale.status_code == 200, sale.text
            sid = sale.json()["id"]
            assert (await c.post(base + "/sales", json=payload)).json()["id"] == sid
            assert (await quote("SAVE10")).status_code == 409
            assert (await c.get(base + "/promotions")).json()["items"][0]["used"] == 1
            receipt = (await c.get(base + "/sales/" + sid)).json()
            import json

            assert (
                json.loads(receipt["sale"]["promotion_snapshot"])["name"]
                == "Updated name"
            )
            assert receipt["sale"]["discount"] == 336
            pdf = await c.get(f"/api/invoices/{sid}.pdf?tenant={t}&language=ur")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            assert (
                await c.put(
                    base + "/promotions/" + pid,
                    json={**offer, "name": "Later name", "active": False, "version": 2},
                )
            ).status_code == 200
            assert (await c.post(base + "/sales", json=payload)).json()["id"] == sid
            assert (
                await c.post(
                    base + "/sales", json={**payload, "promotion_code": "OTHER"}
                )
            ).status_code == 400
            await post("return", t, id=sid, reason="Promotion return")
            assert (await c.get(base + "/promotions?include_inactive=true")).json()[
                "items"
            ][0]["used"] == 1
            # BOGO targeted tax allocation; no tax reduction on the unrelated item.
            tax = await c.post(
                base + "/tax-profiles",
                json=dict(name="Included tax", rate_bps=1800, inclusive=True),
            )
            assert tax.status_code == 201
            assert (
                await c.put(
                    base + "/products/" + a,
                    json=dict(
                        name="Tea",
                        category="General",
                        price=1180,
                        cost=500,
                        reorder=1,
                        tax_profile_id=tax.json()["id"],
                    ),
                )
            ).status_code == 200
            assert (
                await c.put(base + "/tax-settings", json=dict(mode="configured"))
            ).status_code == 200
            bogo = dict(
                code="BOGO",
                name="Buy one get one",
                kind="bogo",
                components=[dict(product=a, quantity=1)],
            )
            assert (await c.post(base + "/promotions", json=bogo)).status_code == 201
            q = (await quote("BOGO")).json()
            assert q["discount"] == 1180 and q["tax"] == 180 and q["total"] == 2180
            sale = await c.post(
                base + "/sales",
                json={
                    **payload,
                    "request": uuid.uuid4().hex,
                    "promotion_code": "BOGO",
                    "quote_token": q["quote_token"],
                    "expected": q["total"],
                    "tendered": q["total"],
                },
            )
            assert sale.status_code == 200, sale.text
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE sales SET created=now()-interval '1 day' WHERE tenant=$1", t
                )
            report = (await c.get(base + "/management-report")).json()
            assert {p["id"]: p["net_sales"] for p in report["products"]} == {
                a: 1000,
                b: 1000,
            }
            assert (
                await c.post(
                    base + "/held-bills",
                    json=dict(
                        id="held-" + uuid.uuid4().hex,
                        label="BOGO held",
                        items=cart,
                        promotion_code="BOGO",
                    ),
                )
            ).status_code == 200
            assert (await c.get(base + "/held-bills")).json()["items"][0]["payload"][
                "promotion_code"
            ] == "BOGO"
            email = uuid.uuid4().hex + "@example.com"
            await post(
                "member",
                t,
                email=email,
                name="Cashier",
                role="Cashier",
                password="CashierPassword2026!",
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as cashier:
                assert (
                    await cashier.post(
                        "/api/auth/login",
                        json=dict(email=email, password="CashierPassword2026!"),
                    )
                ).status_code == 200
                assert (await cashier.get(base + "/promotions")).status_code == 200
                assert (
                    await cashier.post(base + "/promotions", json=offer)
                ).status_code == 403
                assert (
                    await cashier.get(base + "/promotions?include_inactive=true")
                ).status_code == 403
                assert (
                    await cashier.get(f"/api/v1/tenants/{other}/promotions")
                ).status_code == 403


def test_weekday_overnight_anchor_and_date_boundaries():
    from zoneinfo import ZoneInfo
    from app.api.promotions import Promotion
    from pydantic import ValidationError

    tz = ZoneInfo("Asia/Karachi")
    sunday = date(2026, 10, 25)
    scheduled = rule(
        weekdays=[6],
        starts_on=sunday,
        ends_on=sunday,
        starts_minute=22 * 60,
        ends_minute=2 * 60,
    )
    for value in [
        datetime(2026, 10, 25, 22, tzinfo=tz),
        datetime(2026, 10, 26, 1, 59, tzinfo=tz),
    ]:
        assert evaluate(scheduled, [], products(), value)["discount"] == 336
    for value in [
        datetime(2026, 10, 25, 21, 59, tzinfo=tz),
        datetime(2026, 10, 25, 1, tzinfo=tz),
        datetime(2026, 10, 26, 2, tzinfo=tz),
        datetime(2026, 10, 26, 22, tzinfo=tz),
    ]:
        with pytest.raises(HTTPException):
            evaluate(scheduled, [], products(), value)
    assert (
        evaluate(
            rule(weekdays=[6]), [], products(), datetime(2026, 10, 25, 0, tzinfo=tz)
        )["discount"]
        == 336
    )
    with pytest.raises(HTTPException):
        evaluate(rule(weekdays=[0]), [], products(), NOW)
    assert Promotion(
        code="NIGHT",
        name="Night",
        kind="fixed",
        value=100,
        weekdays=[6],
        starts_minute=1320,
        ends_minute=120,
    )
    for changes in [
        dict(weekdays=[]),
        dict(weekdays=[0, 0]),
        dict(weekdays=[7]),
        dict(weekdays=[True]),
        dict(starts_minute=120, ends_minute=120),
        dict(starts_minute=120),
    ]:
        with pytest.raises(ValidationError):
            Promotion(code="BAD", name="Invalid", kind="fixed", value=100, **changes)
