"""Supplier accounting checks: match limits, isolation, retries and reversible audit records."""

import os, uuid
from datetime import date, timedelta
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_supplier_invoice_payment_matching_and_voids():
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
        ) as c:
            assert (
                await c.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200
            tid = (
                await c.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Supplier finance",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"
            path = base + "/payables"
            p = (
                await c.post(
                    base + "/products",
                    json={
                        "sku": "BILL",
                        "name": "Matched item",
                        "category": "General",
                        "price": 500,
                        "initial": 0,
                    },
                )
            ).json()["id"]
            supplier = (
                await c.post(
                    base + "/suppliers",
                    json={"name": "Test supplier", "contact": "", "lead_days": 7},
                )
            ).json()["id"]
            po = (
                await c.post(
                    base + "/purchase-orders",
                    json={
                        "request": uuid.uuid4().hex,
                        "supplier": supplier,
                        "reference": "PO-1",
                        "lines": [{"product": p, "quantity": 10, "unit_cost": 200}],
                    },
                )
            ).json()["id"]
            d = date.today() - timedelta(days=40)
            bill = {
                "request": uuid.uuid4().hex,
                "purchase": po,
                "invoice_number": "SUP-1",
                "invoice_date": d.isoformat(),
                "due_date": (d + timedelta(days=1)).isoformat(),
                "tax": 100,
                "lines": [{"product": p, "quantity": 4, "unit_cost": 200}],
            }
            assert (await c.post(path, json=bill)).status_code == 409  # not received
            assert (
                await c.post(
                    base + f"/purchase-orders/{po}/receipts",
                    json={
                        "request": uuid.uuid4().hex,
                        "lines": [{"product": p, "quantity": 5}],
                    },
                )
            ).status_code == 200
            bad = {**bill, "lines": [{"product": p, "quantity": 4, "unit_cost": 201}]}
            assert (await c.post(path, json=bad)).status_code == 409
            r = await c.post(path, json=bill)
            assert r.status_code == 201, r.text
            bid = r.json()["id"]
            bp = path + "/" + bid
            assert (await c.post(path, json=bill)).json()["id"] == bid
            assert (await c.post(path, json={**bill, "tax": 101})).status_code == 409
            assert (
                await c.post(path, json={**bill, "request": uuid.uuid4().hex})
            ).status_code == 409
            bill2 = {
                **bill,
                "request": uuid.uuid4().hex,
                "invoice_number": "SUP-2",
                "lines": [{"product": p, "quantity": 2, "unit_cost": 200}],
            }
            assert (
                await c.post(path, json=bill2)
            ).status_code == 409  # only 1 received unbilled
            match = (await c.get(path + "/matchable-orders")).json()["items"]
            assert match[0]["lines"][0]["unbilled"] == 1
            detail = (await c.get(bp)).json()
            assert detail["bill"]["total"] == 900
            lookups = (await c.get(base + "/lookups?kind=payment_method")).json()[
                "items"
            ]
            method = lookups[0]["id"]
            payment = {
                "request": uuid.uuid4().hex,
                "amount": 400,
                "method_id": method,
                "reference": "Bank transfer 123",
                "paid_on": date.today().isoformat(),
            }
            r = await c.post(bp + "/payments", json=payment)
            assert r.status_code == 201, r.text
            payid = r.json()["id"]
            assert (await c.post(bp + "/payments", json=payment)).json()["id"] == payid
            assert (
                await c.post(bp + "/payments", json={**payment, "amount": 401})
            ).status_code == 409
            assert (
                await c.post(
                    bp + "/payments",
                    json={**payment, "request": uuid.uuid4().hex, "amount": 501},
                )
            ).status_code == 409
            summary = (await c.get(path)).json()["summary"]
            assert (
                summary["outstanding"] == 500 and summary["days_31_plus"] == 500
            ), summary
            assert (
                await c.post(
                    bp + "/void", json={"reason": "Must correct payment first"}
                )
            ).status_code == 409
            # Tenant isolation and lookup ownership.
            other = (
                await c.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Other finance",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            assert (
                await c.get(f"/api/v1/tenants/{other}/payables/{bid}")
            ).status_code == 404
            foreign = (
                await c.get(f"/api/v1/tenants/{other}/lookups?kind=payment_method")
            ).json()["items"][0]["id"]
            r = await c.post(
                bp + "/payments",
                json={**payment, "request": uuid.uuid4().hex, "method_id": foreign},
            )
            assert r.status_code in (400, 404), r.text
            assert (
                await c.post(
                    bp + f"/payments/{payid}/void",
                    json={"reason": "Duplicate bank entry"},
                )
            ).status_code == 200
            assert (
                await c.post(bp + f"/payments/{payid}/void", json={"reason": "Retry"})
            ).status_code == 200
            assert (await c.get(path)).json()["summary"]["outstanding"] == 900
            assert (
                await c.post(
                    bp + "/void", json={"reason": "Supplier issued correction"}
                )
            ).status_code == 200
            assert (await c.get(path)).json()["summary"]["outstanding"] == 0
            assert (
                await c.post(
                    bp + "/payments", json={**payment, "request": uuid.uuid4().hex}
                )
            ).status_code == 409
            assert (await c.get(path + "/matchable-orders")).json()["items"][0][
                "lines"
            ][0]["unbilled"] == 5
            assert (await c.get(bp)).json()["payments"][0]["status"] == "void"
            # Stock and payments do not silently update each other.
            assert (await c.get(base + "/products")).json()["items"][0]["stock"] == 5
            for role in ("Cashier", "Stock Manager"):
                email = uuid.uuid4().hex + "@example.com"
                password = "RestrictedPassword2026!"
                assert (
                    await c.post(
                        "/api/workspace",
                        json={
                            "action": "member",
                            "tenant": tid,
                            "email": email,
                            "name": role,
                            "password": password,
                            "role": role,
                        },
                    )
                ).status_code == 200
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                    headers={"Origin": config.APP_ORIGIN},
                ) as staff:
                    await staff.post(
                        "/api/auth/login", json={"email": email, "password": password}
                    )
                    assert (await staff.get(path)).status_code == 403
                    assert (await staff.post(path, json=bill2)).status_code == 403
