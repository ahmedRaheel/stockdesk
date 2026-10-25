"""Supplier returns: source quantity, exact credit allocation, and refund reconciliation."""

import os, uuid
from datetime import date
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_supplier_returns_credits_refunds_and_replay():
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
            await c.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )
            tid = (
                await c.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Returns test",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"

            async def lookup(kind, code=None):
                items = (await c.get(base + "/lookups", params={"kind": kind})).json()[
                    "items"
                ]
                return next(
                    (x["id"] for x in items if x["code"] == code), items[0]["id"]
                )

            pid = (
                await c.post(
                    base + "/products",
                    json={
                        "sku": "RETURN",
                        "name": "Weighted item",
                        "category": "General",
                        "unit_id": await lookup("unit", "kg"),
                        "price": 1000,
                        "initial": 0,
                    },
                )
            ).json()["id"]
            supplier = (
                await c.post(base + "/suppliers", json={"name": "Returns supplier"})
            ).json()["id"]
            po = (
                await c.post(
                    base + "/purchase-orders",
                    json={
                        "request": uuid.uuid4().hex,
                        "supplier": supplier,
                        "lines": [{"product": pid, "quantity": 3, "unit_cost": 101}],
                    },
                )
            ).json()["id"]
            receipt = {
                "request": uuid.uuid4().hex,
                "lines": [{"product": pid, "quantity": 3, "lot": "LOT-A"}],
            }
            assert (
                await c.post(base + f"/purchase-orders/{po}/receipts", json=receipt)
            ).status_code == 200
            assert (
                await c.post(base + f"/purchase-orders/{po}/receipts", json=receipt)
            ).status_code == 200
            from app.api.payables import today

            d = today().isoformat()
            bill = (
                await c.post(
                    base + "/payables",
                    json={
                        "request": uuid.uuid4().hex,
                        "purchase": po,
                        "invoice_number": "B-001",
                        "invoice_date": d,
                        "due_date": d,
                        "tax": 30,
                        "lines": [{"product": pid, "quantity": 3, "unit_cost": 101}],
                    },
                )
            ).json()["id"]
            path = base + "/payables/" + bill
            src = (await c.get(path + "/return-options")).json()["items"]
            assert len(src) == 1
            source = src[0]["movement"]
            reason = await lookup("supplier_return_reason")
            method = await lookup("payment_method")
            credit = {
                "request": uuid.uuid4().hex,
                "credit_number": "C-001",
                "returned_on": d,
                "reason_id": reason,
                "reason": "Damaged packaging",
                "tax": 10,
                "lines": [{"source": source, "quantity": 1}],
            }
            assert (
                await c.post(
                    path + "/returns",
                    json={**credit, "lines": [{"source": source, "quantity": 4}]},
                )
            ).status_code == 409
            assert (
                await c.post(path + "/returns", json={**credit, "tax": 31})
            ).status_code == 409
            # A valid receipt is not enough if the physical batch has since moved.
            movement = {
                "request": uuid.uuid4().hex,
                "product": pid,
                "type": "OUT",
                "quantity": 2,
                "notes": "Stock sold elsewhere",
                "batch_id": src[0]["batch"],
            }
            assert (
                await c.post(base + "/stock-adjustments", json=movement)
            ).status_code == 200
            assert (
                await c.post(
                    path + "/returns",
                    json={**credit, "lines": [{"source": source, "quantity": 2}]},
                )
            ).status_code == 409
            assert (await c.get(path)).json()["credits"] == []
            assert (
                await c.post(
                    base + "/stock-adjustments",
                    json={
                        "request": uuid.uuid4().hex,
                        "product": pid,
                        "type": "IN",
                        "quantity": 2,
                        "notes": "Restore test batch",
                        "lot": "LOT-A",
                    },
                )
            ).status_code == 200
            r = await c.post(path + "/returns", json=credit)
            assert r.status_code == 201, r.text
            assert (await c.post(path + "/returns", json=credit)).json()[
                "id"
            ] == r.json()["id"]
            assert (
                await c.post(path + "/returns", json={**credit, "tax": 9})
            ).status_code == 409
            assert (await c.get(base + "/products")).json()["items"][0]["stock"] == 2
            detail = (await c.get(path)).json()
            assert detail["credited"] == 111
            # Balance is now 222. Payment above it must not use the original invoice total.
            payment = {
                "request": uuid.uuid4().hex,
                "amount": 223,
                "method_id": method,
                "reference": "PAY-001",
                "paid_on": d,
            }
            assert (await c.post(path + "/payments", json=payment)).status_code == 409
            assert (
                await c.post(path + "/payments", json={**payment, "amount": 222})
            ).status_code == 201
            credit2 = {
                **credit,
                "request": uuid.uuid4().hex,
                "credit_number": "C-002",
                "tax": 20,
                "lines": [{"source": source, "quantity": 2}],
            }
            r = await c.post(path + "/returns", json=credit2)
            assert r.status_code == 201, r.text
            summary = (await c.get(base + "/payables")).json()["summary"]
            assert (
                summary["outstanding"] == 0 and summary["supplier_credit"] == 222
            ), summary
            assert (await c.get(base + "/products")).json()["items"][0]["stock"] == 0
            refund = {
                "request": uuid.uuid4().hex,
                "amount": 100,
                "method_id": method,
                "reference": "REF-001",
                "received_on": d,
            }
            r = await c.post(path + "/refunds", json=refund)
            assert r.status_code == 201, r.text
            refund_id = r.json()["id"]
            assert (await c.post(path + "/refunds", json=refund)).json()[
                "id"
            ] == refund_id
            assert (
                await c.post(path + "/refunds", json={**refund, "amount": 99})
            ).status_code == 409
            assert (
                await c.post(
                    path + "/refunds",
                    json={**refund, "request": uuid.uuid4().hex, "amount": 123},
                )
            ).status_code == 409
            assert (await c.get(base + "/payables")).json()["summary"][
                "supplier_credit"
            ] == 122
            assert (
                await c.post(
                    path + f"/refunds/{refund_id}/void",
                    json={"reason": "Incorrect refund reference"},
                )
            ).status_code == 200
            assert (
                await c.post(
                    path + f"/refunds/{refund_id}/void", json={"reason": "Retry"}
                )
            ).status_code == 200
            assert (await c.get(base + "/payables")).json()["summary"][
                "supplier_credit"
            ] == 222
            assert (
                await c.post(
                    path + "/void", json={"reason": "Cannot remove stock credit"}
                )
            ).status_code == 409
            assert (
                await c.post(
                    path + "/returns",
                    json={
                        **credit,
                        "request": uuid.uuid4().hex,
                        "credit_number": "C-003",
                    },
                )
            ).status_code == 409
            other = (
                await c.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Other return",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            assert (
                await c.get(f"/api/v1/tenants/{other}/payables/{bill}/return-options")
            ).status_code == 404
            # Three fractional returns must credit the original rounded line exactly.
            po2 = (
                await c.post(
                    base + "/purchase-orders",
                    json={
                        "request": uuid.uuid4().hex,
                        "supplier": supplier,
                        "lines": [
                            {"product": pid, "quantity": 0.003, "unit_cost": 333}
                        ],
                    },
                )
            ).json()["id"]
            await c.post(
                base + f"/purchase-orders/{po2}/receipts",
                json={
                    "request": uuid.uuid4().hex,
                    "lines": [{"product": pid, "quantity": 0.003, "lot": "TINY"}],
                },
            )
            bill2 = (
                await c.post(
                    base + "/payables",
                    json={
                        "request": uuid.uuid4().hex,
                        "purchase": po2,
                        "invoice_number": "B-TINY",
                        "invoice_date": d,
                        "due_date": d,
                        "lines": [
                            {"product": pid, "quantity": 0.003, "unit_cost": 333}
                        ],
                    },
                )
            ).json()["id"]
            path2 = base + "/payables/" + bill2
            source2 = (await c.get(path2 + "/return-options")).json()["items"][0][
                "movement"
            ]
            # A valid first line followed by a foreign source must not post anything.
            failed = {
                **credit,
                "request": uuid.uuid4().hex,
                "credit_number": "BAD-MIX",
                "tax": 0,
                "lines": [
                    {"source": source2, "quantity": 0.001},
                    {"source": source, "quantity": 0.001},
                ],
            }
            assert (await c.post(path2 + "/returns", json=failed)).status_code == 404
            assert (await c.get(path2)).json()["credits"] == []
            assert (await c.get(base + "/products")).json()["items"][0][
                "stock"
            ] == 0.003
            for n in range(3):
                r = await c.post(
                    path2 + "/returns",
                    json={
                        **credit,
                        "request": uuid.uuid4().hex,
                        "credit_number": f"TINY-{n}",
                        "tax": 0,
                        "lines": [{"source": source2, "quantity": 0.001}],
                    },
                )
                assert r.status_code == 201, r.text
            assert (await c.get(path2)).json()["credited"] == 1
            assert (await c.get(base + "/products")).json()["items"][0]["stock"] == 0
            email = uuid.uuid4().hex + "@example.com"
            pwd = "StockOnlyPassword2026!"
            await c.post(
                "/api/workspace",
                json={
                    "action": "member",
                    "tenant": tid,
                    "email": email,
                    "name": "Stock clerk",
                    "password": pwd,
                    "role": "Stock Manager",
                },
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Origin": config.APP_ORIGIN},
            ) as staff:
                await staff.post(
                    "/api/auth/login", json={"email": email, "password": pwd}
                )
                assert (await staff.get(path + "/return-options")).status_code == 403
                assert (
                    await staff.post(path + "/returns", json=credit)
                ).status_code == 403
