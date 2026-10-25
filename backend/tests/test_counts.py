"""Counts must not overwrite sales and may only post once with independent approval."""

import os, uuid
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_batch_counts_approval_revision_and_exactly_once():
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
            base_url="http://testserver",
            headers={"Origin": config.APP_ORIGIN},
        ) as owner:
            assert (
                await owner.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200
            tid = (
                await owner.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Counting store",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"
            email = "counter-" + uuid.uuid4().hex + "@example.com"
            password = "CounterPassword2026!"
            r = await owner.post(
                "/api/workspace",
                json={
                    "action": "member",
                    "tenant": tid,
                    "email": email,
                    "name": "Counter",
                    "password": password,
                    "role": "Stock Manager",
                },
            )
            assert r.status_code == 200, r.text
            units = (
                await owner.get(base + "/lookups", params={"kind": "unit"})
            ).json()["items"]
            unit = next(x["id"] for x in units if x["code"] == "piece")
            r = await owner.post(
                base + "/products",
                json={
                    "sku": "COUNT",
                    "name": "Counting item",
                    "category": "General",
                    "unit_id": unit,
                    "price": 100,
                    "initial": 10,
                },
            )
            assert r.status_code == 201, r.text
            pid = r.json()["id"]
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Origin": config.APP_ORIGIN},
            ) as counter:
                assert (
                    await counter.post(
                        "/api/auth/login", json={"email": email, "password": password}
                    )
                ).status_code == 200
                create = {
                    "request": uuid.uuid4().hex,
                    "reference": "Shelf A",
                    "products": [pid],
                }
                r = await counter.post(base + "/stock-counts", json=create)
                assert r.status_code == 201, r.text
                cid = r.json()["id"]
                path = base + "/stock-counts/" + cid
                assert (await counter.post(base + "/stock-counts", json=create)).json()[
                    "id"
                ] == cid
                assert (
                    await counter.post(
                        base + "/stock-counts", json={**create, "reference": "Changed"}
                    )
                ).status_code == 409
                d = (await counter.get(path)).json()
                batch = d["lines"][0]["batch"]
                assert d["lines"][0]["expected"] == 10
                assert (
                    await counter.post(path + "/submit", json={})
                ).status_code == 400
                assert (
                    await counter.put(
                        path + "/lines",
                        json={"lines": [{"batch": batch, "counted": 8.5}]},
                    )
                ).status_code == 400
                assert (
                    await counter.put(
                        path + "/lines",
                        json={"lines": [{"batch": batch, "counted": 8}]},
                    )
                ).status_code == 200
                assert (
                    await counter.post(path + "/submit", json={})
                ).status_code == 200
                assert (
                    await counter.post(
                        path + "/post", json={"note": "Own approval denied"}
                    )
                ).status_code == 403
                posted = await owner.post(
                    path + "/post", json={"note": "Verified physical count"}
                )
                assert posted.status_code == 200, posted.text
                assert (
                    await owner.post(path + "/post", json={"note": "Retry"})
                ).json()["replayed"]
                assert (await owner.get(base + "/products")).json()["items"][0][
                    "stock"
                ] == 8
                assert (
                    await counter.put(
                        path + "/lines",
                        json={"lines": [{"batch": batch, "counted": 5}]},
                    )
                ).status_code == 409
                assert (
                    await owner.post(
                        path + "/cancel", json={"note": "Cannot cancel posted"}
                    )
                ).status_code == 409
                # A zero-net stock change still invalidates a count's revision fence.
                create["request"] = uuid.uuid4().hex
                cid = (await counter.post(base + "/stock-counts", json=create)).json()[
                    "id"
                ]
                path = base + "/stock-counts/" + cid
                assert (
                    await counter.put(
                        path + "/lines",
                        json={"lines": [{"batch": batch, "counted": 9}]},
                    )
                ).status_code == 200
                assert (
                    await counter.post(path + "/submit", json={})
                ).status_code == 200
                for kind in ("OUT", "IN"):
                    r = await owner.post(
                        base + "/stock-adjustments",
                        json={
                            "request": uuid.uuid4().hex,
                            "product": pid,
                            "type": kind,
                            "quantity": 1,
                            "notes": "Movement during count",
                        },
                    )
                    assert r.status_code == 200, r.text
                assert (
                    await owner.post(path + "/post", json={"note": "Must recount"})
                ).status_code == 409
                assert (await owner.get(base + "/products")).json()["items"][0][
                    "stock"
                ] == 8
                assert (
                    await counter.post(
                        path + "/cancel",
                        json={"note": "Movement conflict; recount required"},
                    )
                ).status_code == 200
                # Counts made by an owner still require another approver.
                create["request"] = uuid.uuid4().hex
                cid = (await owner.post(base + "/stock-counts", json=create)).json()[
                    "id"
                ]
                path = base + "/stock-counts/" + cid
                assert (
                    await owner.put(
                        path + "/lines",
                        json={"lines": [{"batch": batch, "counted": 7}]},
                    )
                ).status_code == 200
                assert (await owner.post(path + "/submit", json={})).status_code == 200
                assert (
                    await owner.post(path + "/post", json={"note": "Self approval"})
                ).status_code == 403
                other = (
                    await owner.post(
                        "/api/workspace",
                        json={
                            "action": "tenant",
                            "name": "Other count",
                            "currency": "PKR",
                        },
                    )
                ).json()["id"]
                assert (
                    await owner.get(f"/api/v1/tenants/{other}/stock-counts/{cid}")
                ).status_code == 404
