"""Purchasing policy, maker/checker decisions and supplier quote isolation."""

import os
import uuid
from datetime import timedelta
import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_procurement_controls_and_quotes():
    from app import config, db
    from app.main import app
    from app.api.payables import today

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
        ) as owner, httpx.AsyncClient(
            transport=transport,
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as staff:
            assert (
                await owner.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200

            async def tenant(name):
                r = await owner.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": name, "currency": "PKR"},
                )
                assert r.status_code == 200, r.text
                return r.json()["id"]

            tid = await tenant("Procurement controls")
            other = await tenant("Other procurement")
            base = f"/api/v1/tenants/{tid}"
            email = uuid.uuid4().hex + "@example.com"
            pwd = "PurchaserPassword2026!"
            assert (
                await owner.post(
                    "/api/workspace",
                    json={
                        "action": "member",
                        "tenant": tid,
                        "email": email,
                        "name": "Buyer",
                        "password": pwd,
                        "role": "Manager",
                    },
                )
            ).status_code == 200
            assert (
                await staff.post(
                    "/api/auth/login", json={"email": email, "password": pwd}
                )
            ).status_code == 200
            r = await owner.post(
                base + "/products",
                json={
                    "sku": "TEST",
                    "name": "Whole unit",
                    "category": "General",
                    "price": 200,
                    "cost": 100,
                    "initial": 0,
                },
            )
            assert r.status_code == 201, r.text
            product = (await owner.get(base + "/products")).json()["items"][0]["id"]
            a = (
                await owner.post(
                    base + "/suppliers", json={"name": "Vendor A", "lead_days": 2}
                )
            ).json()["id"]
            b = (
                await owner.post(
                    base + "/suppliers", json={"name": "Vendor B", "lead_days": 3}
                )
            ).json()["id"]
            assert (
                len((await owner.get(base + "/suppliers?q=Vendor%20B")).json()["items"])
                == 1
            )
            assert (await owner.get(base + "/purchasing-policy")).json() == {
                "enabled": False,
                "threshold": 0,
                "version": 0,
            }
            policy = {"enabled": True, "threshold": 1000, "version": 0}
            assert (
                await staff.put(base + "/purchasing-policy", json=policy)
            ).status_code == 403
            assert (
                await owner.put(base + "/purchasing-policy", json=policy)
            ).status_code == 200
            assert (
                await owner.put(base + "/purchasing-policy", json=policy)
            ).status_code == 409

            async def order(client=staff, cost=100):
                r = await client.post(
                    base + "/purchase-orders",
                    json={
                        "request": uuid.uuid4().hex,
                        "supplier": a,
                        "reference": "Approval test",
                        "lines": [
                            {"product": product, "quantity": 10, "unit_cost": cost}
                        ],
                    },
                )
                assert r.status_code == 200, r.text
                return r.json()["id"]

            oid = await order()

            async def orders():
                return {
                    x["id"]: x
                    for x in (await owner.get(base + "/purchase-orders")).json()[
                        "items"
                    ]
                }

            assert (await orders())[oid]["status"] == "pending_approval"
            under = await order(cost=99)
            assert (await orders())[under]["status"] == "open"
            # Threshold is frozen per order; turning policy off cannot release a pending order.
            assert (
                await owner.put(
                    base + "/purchasing-policy",
                    json={"enabled": False, "threshold": 999999, "version": 1},
                )
            ).status_code == 200
            assert (await orders())[oid]["approval_threshold"] == 1000
            receipt = {
                "request": uuid.uuid4().hex,
                "lines": [{"product": product, "quantity": 10}],
            }
            url = base + f"/purchase-orders/{oid}"
            assert (
                await staff.post(url + "/receipts", json=receipt)
            ).status_code == 409
            decision = {"decision": "approve", "note": "Budget checked"}
            assert (
                await staff.post(url + "/decision", json=decision)
            ).status_code == 403
            assert (
                await owner.post(
                    f"/api/v1/tenants/{other}/purchase-orders/{oid}/decision",
                    json=decision,
                )
            ).status_code == 404
            assert (
                await owner.post(url + "/decision", json=decision)
            ).status_code == 200
            assert (await owner.post(url + "/decision", json=decision)).json()[
                "replayed"
            ]
            assert (
                await owner.post(
                    url + "/decision", json={**decision, "note": "Different"}
                )
            ).status_code == 409
            r = await staff.post(url + "/receipts", json=receipt)
            assert r.status_code == 200, r.text
            assert (await orders())[oid]["status"] == "received"
            assert (
                await owner.put(
                    base + "/purchasing-policy",
                    json={"enabled": True, "threshold": 0, "version": 2},
                )
            ).status_code == 200
            rejected = await order()
            rurl = base + f"/purchase-orders/{rejected}"
            assert (
                await owner.post(
                    rurl + "/decision",
                    json={"decision": "reject", "note": "Duplicate request"},
                )
            ).status_code == 200
            assert (
                await staff.post(
                    rurl + "/receipts", json={**receipt, "request": uuid.uuid4().hex}
                )
            ).status_code == 409
            assert (await staff.post(rurl + "/cancel")).status_code == 409
            own = await order(owner)
            assert (
                await owner.post(
                    base + f"/purchase-orders/{own}/decision", json=decision
                )
            ).status_code == 403
            # Owner-created orders require another authorized user too.
            assert (
                await staff.post(
                    base + f"/purchase-orders/{own}/decision", json=decision
                )
            ).status_code == 200
            quote = {
                "supplier": a,
                "product": product,
                "unit_cost": 120,
                "minimum_quantity": 5,
                "lead_days": 2,
                "valid_from": str(today()),
                "valid_until": str(today() + timedelta(days=3)),
                "active": True,
                "notes": "Case pricing",
            }
            r = await staff.post(base + "/supplier-offers", json=quote)
            assert r.status_code == 201, r.text
            qid = r.json()["id"]
            assert (
                await staff.post(base + "/supplier-offers", json=quote)
            ).status_code == 409
            assert (
                await staff.post(
                    base + "/supplier-offers",
                    json={**quote, "supplier": b, "minimum_quantity": 1.5},
                )
            ).status_code == 400
            assert (
                await staff.post(
                    base + "/supplier-offers",
                    json={
                        **quote,
                        "supplier": b,
                        "valid_until": str(today() - timedelta(days=1)),
                    },
                )
            ).status_code == 400
            assert (
                await owner.post(f"/api/v1/tenants/{other}/supplier-offers", json=quote)
            ).status_code == 404
            r = await staff.post(
                base + "/supplier-offers",
                json={**quote, "supplier": b, "unit_cost": 100, "minimum_quantity": 1},
            )
            assert r.status_code == 201, r.text

            async def offers(params=""):
                return (await owner.get(base + "/supplier-offers?" + params)).json()[
                    "items"
                ]

            assert len(await offers("eligible=true&quantity=1")) == 1
            assert [
                x["supplier"] for x in await offers("eligible=true&quantity=5")
            ] == [b, a]
            update = {**quote, "version": 1, "unit_cost": 90}
            assert (
                await staff.put(base + f"/supplier-offers/{qid}", json=update)
            ).status_code == 200
            assert (
                await staff.put(base + f"/supplier-offers/{qid}", json=update)
            ).status_code == 409
            assert [
                x["supplier"] for x in await offers("eligible=true&quantity=5")
            ] == [a, b]
            assert (
                await staff.put(
                    base + f"/supplier-offers/{qid}",
                    json={**update, "version": 2, "active": False},
                )
            ).status_code == 200
            assert len(await offers("eligible=true&quantity=5")) == 1
            assert len(await offers("q=vendor%20a")) == 1
            # Permission revocation applies to quotes and approval, not just navigation.
            assert (
                await owner.post(
                    "/api/workspace",
                    json={
                        "action": "member",
                        "tenant": tid,
                        "email": email,
                        "name": "Buyer",
                        "role": "Cashier",
                    },
                )
            ).status_code == 200
            assert (await staff.get(base + "/supplier-offers")).status_code == 403
            assert (
                await staff.post(
                    base + f"/purchase-orders/{own}/decision", json=decision
                )
            ).status_code == 403
            r = await owner.get(base + "/supplier-performance")
            assert r.status_code == 200, r.text
            perf = next(x for x in r.json()["items"] if x["id"] == a)
            assert (
                perf["orders"] == 4
                and perf["completed"] == 1
                and perf["open_orders"] == 2
            )
            assert (
                perf["delivery_samples"] == 1 and perf["avg_first_delivery_days"] >= 0
            )
            assert not (
                await owner.get(f"/api/v1/tenants/{other}/supplier-offers")
            ).json()["items"]
