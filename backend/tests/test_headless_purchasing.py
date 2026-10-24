"""Acceptance tests for external clients and atomic goods receiving."""

import os
import uuid
import httpx
import pytest
from pydantic import ValidationError
from app.api.contracts import ProductCreate, PurchaseCreate


def test_public_contract_rejects_fractional_stock_and_unknown_fields():
    valid = dict(sku="RICE-1", name="Rice", category="Pantry", price=100, initial=0)
    assert ProductCreate(**valid).cost == 0
    with pytest.raises(ValidationError):
        ProductCreate(**{**valid, "initial": 1.5})
    with pytest.raises(ValidationError):
        ProductCreate(**{**valid, "tenant": "spoofed"})
    with pytest.raises(ValidationError):
        PurchaseCreate(request="r", supplier="s", lines=[])


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_headless_purchasing_and_atomic_receipts():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            credentials = {
                "email": config.ADMIN_EMAIL,
                "password": config.ADMIN_PASSWORD,
            }
            token = await client.post("/api/v1/auth/token", json=credentials)
            assert token.status_code == 200, token.text
            assert "stockdesk_session" not in client.cookies
            client.headers["Authorization"] = "Bearer " + token.json()["access_token"]
            assert (await client.get("/api/v1/tenants")).status_code == 200
            response = await client.post(
                "/api/workspace",
                json={"action": "tenant", "name": "Purchasing test", "currency": "PKR"},
            )
            assert response.status_code == 200, response.text
            tenant = response.json()["id"]
            other = (
                await client.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": "Other", "currency": "PKR"},
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tenant}"
            for sku in ("RICE", "FLOUR"):
                response = await client.post(
                    base + "/products",
                    json={
                        "sku": sku,
                        "name": sku,
                        "category": "Pantry",
                        "price": 30000,
                        "cost": 20000,
                    },
                )
                assert response.status_code == 201, response.text
            page = (await client.get(base + "/products?limit=1")).json()
            assert page["total"] == 2 and len(page["items"]) == 1
            products = (await client.get(base + "/products")).json()["items"]
            a, b = products[0]["id"], products[1]["id"]
            supplier = await client.post(
                base + "/suppliers",
                json={"name": "Wholesale", "contact": "Buyer desk", "lead_days": 3},
            )
            assert supplier.status_code == 201, supplier.text
            order_payload = {
                "request": str(uuid.uuid4()),
                "supplier": supplier.json()["id"],
                "reference": "PO-TEST",
                "lines": [
                    {"product": a, "quantity": 10, "unit_cost": 18000},
                    {"product": b, "quantity": 5, "unit_cost": 20000},
                ],
            }
            order = await client.post(base + "/purchase-orders", json=order_payload)
            assert order.status_code == 200, order.text
            oid = order.json()["id"]
            assert (
                await client.post(base + "/purchase-orders", json=order_payload)
            ).json()["id"] == oid
            assert (
                await client.post(
                    base + "/purchase-orders",
                    json={**order_payload, "reference": "changed"},
                )
            ).status_code == 409
            # Composite scoping rejects a supplier from another tenant even for an admin.
            cross = await client.post(
                f"/api/v1/tenants/{other}/purchase-orders",
                json={**order_payload, "request": str(uuid.uuid4())},
            )
            assert cross.status_code == 404
            duplicate_lines = {
                **order_payload,
                "request": str(uuid.uuid4()),
                "lines": [order_payload["lines"][0]] * 2,
            }
            assert (
                await client.post(base + "/purchase-orders", json=duplicate_lines)
            ).status_code == 400
            receive_url = base + f"/purchase-orders/{oid}/receipts"
            partial = {
                "request": str(uuid.uuid4()),
                "lines": [{"product": a, "quantity": 4}],
            }
            response = await client.post(receive_url, json=partial)
            assert response.status_code == 200, response.text
            assert (await client.post(receive_url, json=partial)).json()[
                "id"
            ] == response.json()["id"]
            assert (await client.get(base + "/purchase-orders")).json()["items"][0][
                "status"
            ] == "partial"
            # The first valid line must roll back when a later line over-receives.
            invalid = {
                "request": str(uuid.uuid4()),
                "lines": [{"product": a, "quantity": 2}, {"product": b, "quantity": 6}],
            }
            assert (await client.post(receive_url, json=invalid)).status_code == 409
            stock = {
                p["id"]: p["stock"]
                for p in (await client.get(base + "/products")).json()["items"]
            }
            assert stock == {a: 4, b: 0}
            assert (
                await client.post(base + f"/purchase-orders/{oid}/cancel")
            ).status_code == 200
            assert (
                await client.post(
                    receive_url, json={**partial, "request": str(uuid.uuid4())}
                )
            ).status_code == 409
            assert (
                await client.post(receive_url, json=partial)
            ).status_code == 200  # Replay original success after cancellation.
            # A second order completes and cannot then be cancelled.
            payload = {
                **order_payload,
                "request": str(uuid.uuid4()),
                "lines": [{"product": b, "quantity": 1, "unit_cost": 19000}],
            }
            oid2 = (await client.post(base + "/purchase-orders", json=payload)).json()[
                "id"
            ]
            assert (
                await client.post(
                    base + f"/purchase-orders/{oid2}/receipts",
                    json={
                        "request": str(uuid.uuid4()),
                        "lines": [{"product": b, "quantity": 1}],
                    },
                )
            ).status_code == 200
            assert (
                await client.post(base + f"/purchase-orders/{oid2}/cancel")
            ).status_code == 409
            # Token permission is still tenant-role permission, not a shortcut.
            address = f"cashier-{uuid.uuid4().hex}@example.com"
            pwd = "CashierPassword!2026"
            assert (
                await client.post(
                    "/api/workspace",
                    json={
                        "action": "member",
                        "tenant": tenant,
                        "email": address,
                        "name": "Cashier",
                        "password": pwd,
                        "role": "Cashier",
                    },
                )
            ).status_code == 200
            cashier = (
                await client.post(
                    "/api/v1/auth/token", json={"email": address, "password": pwd}
                )
            ).json()["access_token"]
            headers = {"Authorization": "Bearer " + cashier}
            assert (
                await client.get(base + "/suppliers", headers=headers)
            ).status_code == 403
            assert (
                await client.get(f"/api/v1/tenants/{other}/products", headers=headers)
            ).status_code == 403
            invalid = await client.post(base + "/products", json={"price": -1})
            assert invalid.status_code == 422 and "fields" in invalid.json()
            assert "X-Request-ID" in invalid.headers
            schema = (await client.get("/api/openapi.json")).json()
            assert "PurchaseCreate" in schema["components"]["schemas"]
            assert (await client.delete("/api/v1/auth/token")).status_code == 200
            assert (await client.get("/api/v1/tenants")).status_code == 401
            # Cookie-only writes require Origin; bearer validation never falls back to cookies.
            client.headers.pop("Authorization")
            assert (
                await client.post(
                    "/api/auth/login",
                    json=credentials,
                    headers={"Origin": config.APP_ORIGIN},
                )
            ).status_code == 200
            assert (
                await client.post(base + "/suppliers", json={"name": "CSRF"})
            ).status_code == 403
            assert (
                await client.get(
                    base + "/products", headers={"Authorization": "Bearer invalid"}
                )
            ).status_code == 401
