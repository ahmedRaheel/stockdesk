"""Quantity pricing, quote provenance and atomic order selection."""

import json
import os
import uuid
from datetime import timedelta
import httpx
import pytest
from pydantic import ValidationError
from app.api.procurement import Offer


def test_price_tier_contract():
    body = dict(
        supplier="s", product="p", unit_cost=100, lead_days=0, valid_from="2026-01-01"
    )
    for tier in [
        dict(minimum_quantity=0, unit_cost=1),
        dict(minimum_quantity="1.0001", unit_cost=1),
        dict(minimum_quantity=2, unit_cost=1.2),
        dict(minimum_quantity=2, unit_cost=-1),
    ]:
        with pytest.raises(ValidationError):
            Offer(**body, tiers=[tier])
    with pytest.raises(ValidationError):
        Offer(
            **body, tiers=[dict(minimum_quantity=i + 2, unit_cost=1) for i in range(21)]
        )


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_tiers_selection_and_order_provenance():
    from app import config, db
    from app.main import app
    from app.api.payables import today

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

            async def post(path, body, status=200):
                r = await c.post(path, json=body)
                assert r.status_code == status, r.text
                return r.json()

            await post(
                "/api/auth/login",
                dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )
            tid = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Tier prices", currency="PKR"),
                )
            )["id"]
            other = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Other tiers", currency="PKR"),
                )
            )["id"]
            base = f"/api/v1/tenants/{tid}"
            p = (
                await post(
                    base + "/products",
                    dict(
                        sku="TIER",
                        name="Tier whole",
                        category="General",
                        price=500,
                        cost=120,
                    ),
                    201,
                )
            )["id"]
            a = (await post(base + "/suppliers", dict(name="Supplier A"), 201))["id"]
            b = (await post(base + "/suppliers", dict(name="Supplier B"), 201))["id"]
            body = dict(
                supplier=a,
                product=p,
                unit_cost=100,
                minimum_quantity=1,
                lead_days=3,
                valid_from=str(today()),
                valid_until=str(today() + timedelta(days=2)),
                tiers=[
                    dict(minimum_quantity=20, unit_cost=60),
                    dict(minimum_quantity=10, unit_cost=80),
                ],
            )
            qid = (await post(base + "/supplier-offers", body, 201))["id"]
            await post(
                base + "/supplier-offers",
                {**body, "supplier": b, "unit_cost": 90, "tiers": []},
                201,
            )

            async def prices(qty=1, extra=""):
                r = await c.get(
                    base
                    + f"/supplier-offers?product={p}&quantity={qty}&eligible=true"
                    + extra
                )
                assert r.status_code == 200, r.text
                return r.json()["items"]

            assert [x["supplier"] for x in await prices()] == [b, a]
            assert [x["supplier"] for x in await prices(10)] == [a, b]
            assert (await prices(9))[1]["effective_unit_cost"] == 100
            assert (await prices(10))[0]["estimated_total"] == 800
            assert (await prices(20))[0]["effective_unit_cost"] == 60
            assert (await prices(20))[0]["applied_minimum_quantity"] == 20
            assert len(await prices(20, "&supplier=" + a)) == 1
            assert await prices("1.5") == []  # Whole-unit product cannot qualify.
            assert (
                await c.get(base + "/supplier-offers?quantity=1.0001")
            ).status_code == 422
            assert (
                await c.get(base + "/supplier-offers?quantity=NaN")
            ).status_code == 422
            assert (await c.get(f"/api/v1/tenants/{other}/supplier-offers")).json()[
                "items"
            ] == []
            assert (
                await c.put(
                    f"/api/v1/tenants/{other}/supplier-offers/{qid}",
                    json={**body, "version": 1},
                )
            ).status_code == 404
            for tiers in [
                [dict(minimum_quantity=1, unit_cost=50)],
                [dict(minimum_quantity=10, unit_cost=100)],
                [
                    dict(minimum_quantity=10, unit_cost=80),
                    dict(minimum_quantity=10, unit_cost=70),
                ],
                [dict(minimum_quantity="1.5", unit_cost=80)],
            ]:
                r = await c.put(
                    base + f"/supplier-offers/{qid}",
                    json={**body, "version": 1, "tiers": tiers},
                )
                assert r.status_code == 400, r.text
            assert (await prices(20))[0]["version"] == 1
            line = dict(
                product=p, quantity=20, unit_cost=60, quote=dict(id=qid, version=1)
            )
            order = dict(
                request=uuid.uuid4().hex,
                supplier=a,
                reference="Frozen tier",
                lines=[line],
            )
            oid = (await post(base + "/purchase-orders", order))["id"]
            saved = (await c.get(base + "/purchase-orders")).json()["items"][0]
            assert saved["order_total"] == 1200
            snapshot = saved["lines"][0]["quote_snapshot"]
            assert (
                snapshot["version"] == 1
                and snapshot["unit_cost"] == 60
                and float(snapshot["minimum_quantity"]) == 20
            )
            for change, status in [
                (dict(quantity=9), 409),
                (dict(unit_cost=61), 409),
                (dict(quote=dict(id=qid, version=2)), 409),
                (dict(quote=dict(id="unknown", version=1)), 404),
            ]:
                await post(
                    base + "/purchase-orders",
                    {
                        **order,
                        "request": uuid.uuid4().hex,
                        "lines": [{**line, **change}],
                    },
                    status,
                )
            await post(
                base + "/purchase-orders",
                {**order, "request": uuid.uuid4().hex, "supplier": b},
                404,
            )
            # Legacy clients may omit tiers; do not silently delete them.
            no_tiers = {k: v for k, v in body.items() if k != "tiers"}
            r = await c.put(
                base + f"/supplier-offers/{qid}",
                json={**no_tiers, "version": 1, "notes": "Changed terms"},
            )
            assert r.status_code == 200, r.text
            assert len((await prices(20))[0]["tiers"]) == 2
            assert (await post(base + "/purchase-orders", order))[
                "id"
            ] == oid  # Replay even after quote update.
            await post(
                base + "/purchase-orders", {**order, "request": uuid.uuid4().hex}, 409
            )
            r = await c.put(
                base + f"/supplier-offers/{qid}", json={**body, "version": 1}
            )
            assert r.status_code == 409
            assert (await c.get(base + "/purchase-orders")).json()["items"][0]["lines"][
                0
            ]["quote_snapshot"] == snapshot
            # Ineligible date/activity and explicit clearing.
            for version, change in [
                (2, dict(active=False)),
                (3, dict(valid_from=str(today() + timedelta(days=1)))),
                (
                    4,
                    dict(
                        valid_from=str(today() - timedelta(days=2)),
                        valid_until=str(today() - timedelta(days=1)),
                    ),
                ),
            ]:
                r = await c.put(
                    base + f"/supplier-offers/{qid}",
                    json={**body, "version": version, **change},
                )
                assert r.status_code == 200, r.text
                assert not await prices(20, "&supplier=" + a)
                await post(
                    base + "/purchase-orders",
                    {
                        **order,
                        "request": uuid.uuid4().hex,
                        "lines": [{**line, "quote": dict(id=qid, version=version + 1)}],
                    },
                    409,
                )
            r = await c.put(
                base + f"/supplier-offers/{qid}",
                json={**body, "version": 5, "tiers": []},
            )
            assert r.status_code == 200, r.text
            assert (await prices(20, "&supplier=" + a))[0]["tiers"] == []
            # Manual agreed costs remain supported, without invented provenance.
            manual = {
                **order,
                "request": uuid.uuid4().hex,
                "lines": [dict(product=p, quantity=2, unit_cost=77)],
            }
            mid = (await post(base + "/purchase-orders", manual))["id"]
            # Simulate an actual pre-migration request signature and replay it.
            async with db.pool.acquire() as conn:
                original = await conn.fetchval(
                    "SELECT signature FROM purchase_orders WHERE id=$1", mid
                )
                assert '"quote"' not in original
            assert (await post(base + "/purchase-orders", manual))["id"] == mid
            # Fractional thresholds and half-up extended totals.
            units = (await c.get(base + "/lookups?kind=unit")).json()["items"]
            kg = next(u["id"] for u in units if u["fractional"])
            weight = (
                await post(
                    base + "/products",
                    dict(
                        sku="WEIGHT",
                        name="Weight",
                        category="General",
                        price=500,
                        cost=100,
                        unit_id=kg,
                    ),
                    201,
                )
            )["id"]
            await post(
                base + "/supplier-offers",
                {
                    **body,
                    "product": weight,
                    "tiers": [dict(minimum_quantity="1.5", unit_cost=81)],
                },
                201,
            )
            r = await c.get(
                base + f"/supplier-offers?product={weight}&quantity=1.5&eligible=true"
            )
            assert r.json()["items"][0]["estimated_total"] == 122
            # Oversized comparisons cannot offer an unorderable or imprecise total.
            expensive = (
                await c.get(base + "/supplier-offers", params={"supplier": b})
            ).json()["items"][0]
            r = await c.put(
                base + "/supplier-offers/" + expensive["id"],
                json={
                    **body,
                    "supplier": b,
                    "unit_cost": 100_000_000_000,
                    "tiers": [],
                    "version": 1,
                },
            )
            assert r.status_code == 200, r.text
            assert not await prices(2, "&supplier=" + b)
            r = await c.get(
                base + "/supplier-offers", params={"supplier": b, "quantity": 1_000_000}
            )
            assert r.json()["items"][0]["estimated_total"] is None
            # A later invalid line rolls back an earlier valid line and its header.
            await post(
                base + "/purchase-orders",
                {
                    **manual,
                    "request": uuid.uuid4().hex,
                    "lines": [
                        manual["lines"][0],
                        dict(
                            product=weight,
                            quantity=2,
                            unit_cost=100,
                            quote=dict(id="missing", version=1),
                        ),
                    ],
                },
                404,
            )
            # CSRF enforcement on tier writes.
            r = await c.put(
                base + f"/supplier-offers/{qid}",
                json={**body, "version": 6},
                headers={"Origin": "https://evil.example"},
            )
            assert r.status_code == 403
            assert len((await c.get(base + "/purchase-orders")).json()["items"]) == 2
