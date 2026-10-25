"""Custom grants must apply to both APIs without weakening tenant or owner boundaries."""

import os, uuid
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_custom_permissions_revocation_and_escalation():
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
            await owner.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )
            tid = (
                await owner.post(
                    "/api/workspace",
                    json={
                        "action": "tenant",
                        "name": "Custom permissions",
                        "currency": "PKR",
                    },
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"
            path = base + "/roles"
            email = uuid.uuid4().hex + "@example.com"
            pwd = "CustomCashier2026!"
            await owner.post(
                "/api/workspace",
                json={
                    "action": "member",
                    "tenant": tid,
                    "email": email,
                    "name": "Custom staff",
                    "password": pwd,
                    "role": "Cashier",
                },
            )
            members = (await owner.get(path + "/members")).json()["items"]
            member = next(x["id"] for x in members if x["email"] == email)
            owner_member = next(x["id"] for x in members if x["role"] == "Owner")
            await owner.post(
                base + "/products",
                json={
                    "sku": "PRIVATE",
                    "name": "Private cost",
                    "category": "General",
                    "price": 1500,
                    "cost": 900,
                    "initial": 10,
                },
            )
            product = (await owner.get(base + "/products")).json()["items"][0]["id"]
            sale = await owner.post(
                base + "/sales",
                json={
                    "request": uuid.uuid4().hex,
                    "items": [{"id": product, "quantity": 1}],
                    "payment": "cash",
                    "expected": 1500,
                    "tendered": 1500,
                },
            )
            assert sale.status_code == 200, sale.text
            sale_id = sale.json()["id"]
            payload = {
                "name": "Counter operator",
                "name_ur": "کاؤنٹر عملہ",
                "permissions": ["read", "sale"],
            }
            r = await owner.post(path, json=payload)
            assert r.status_code == 201, r.text
            rid = r.json()["id"]
            for bad in [
                {"name": "Owner", "permissions": ["read"]},
                {"name": "Audit without costs", "permissions": ["read", "audit"]},
                {"name": "Escalation", "permissions": ["read", "roles"]},
                {"name": "Escalation", "permissions": ["read", "team"]},
                {"name": "Finance without costs", "permissions": ["read", "finance"]},
            ]:
                assert (await owner.post(path, json=bad)).status_code == 400
            assert (
                await owner.post(
                    path + "/assignments", json={"member": owner_member, "role_id": rid}
                )
            ).status_code == 409
            assert (
                await owner.post(
                    path + "/assignments", json={"member": member, "role_id": rid}
                )
            ).status_code == 200
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Origin": config.APP_ORIGIN},
            ) as staff:
                await staff.post(
                    "/api/auth/login", json={"email": email, "password": pwd}
                )
                snapshot = (
                    await staff.get("/api/workspace", params={"tenant": tid})
                ).json()
                assert snapshot["role"] == "Counter operator"
                assert snapshot["permissions"] == ["read", "sale"]
                assert "cost" not in snapshot["products"][0]
                assert (
                    "cost"
                    not in (await staff.get(base + "/products")).json()["items"][0]
                )
                for endpoint in [
                    "/roles",
                    "/payables",
                    "/management-report",
                    "/stock-counts",
                    "/audit-events",
                ]:
                    assert (
                        await staff.get(base + endpoint)
                    ).status_code == 403, endpoint
                assert (
                    await staff.post(
                        "/api/workspace",
                        json={
                            "action": "member",
                            "tenant": tid,
                            "email": email,
                            "role": "Owner",
                        },
                    )
                ).status_code == 403
                receipt = (await staff.get(base + "/sales/" + sale_id)).json()
                assert "cost" not in receipt["items"][0]
                legacy = (
                    await staff.get(
                        "/api/workspace", params={"tenant": tid, "receipt": sale_id}
                    )
                ).json()
                assert "cost" not in legacy["items"][0]
                # Updating the role affects the existing session on its next request.
                updated = {
                    **payload,
                    "name": "Finance reviewer",
                    "permissions": ["read", "cost", "finance", "audit"],
                    "version": 1,
                    "active": True,
                }
                assert (
                    await owner.put(path + "/" + rid, json=updated)
                ).status_code == 200
                assert (
                    await owner.put(path + "/" + rid, json=updated)
                ).status_code == 409
                assert (await staff.get(base + "/payables")).status_code == 200
                snapshot = (
                    await staff.get("/api/workspace", params={"tenant": tid})
                ).json()
                assert snapshot["products"][0]["cost"] == 900 and snapshot["audit"]
                events = (
                    await staff.get(
                        base + "/audit-events",
                        params={"q": "Custom role saved", "limit": 1},
                    )
                ).json()
                assert events["total"] == 2 and len(events["items"]) == 1
                assert events["timezone"] == "UTC"
                assert (
                    await staff.get(
                        base + "/audit-events", params={"q": "no-matching-event"}
                    )
                ).json()["total"] == 0
                assert (
                    await staff.get(
                        base + "/audit-events",
                        params={"start": "2026-12-31", "end": "2026-01-01"},
                    )
                ).status_code == 400

                assert (await staff.get(base + "/sales/not-a-sale")).status_code == 403
                assert (
                    await owner.put(
                        path + "/" + rid,
                        json={**updated, "version": 2, "active": False},
                    )
                ).status_code == 200
                assert (await staff.get(base + "/products")).status_code == 403
                # Restoring a built-in role explicitly clears custom assignment.
                assert (
                    await owner.post(
                        "/api/workspace",
                        json={
                            "action": "member",
                            "tenant": tid,
                            "email": email,
                            "role": "Cashier",
                        },
                    )
                ).status_code == 200
                assert (await staff.get(base + "/products")).status_code == 200
                assert (await staff.get(base + "/payables")).status_code == 403
            other = (
                await owner.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": "Other roles", "currency": "PKR"},
                )
            ).json()["id"]
            r = await owner.post(
                f"/api/v1/tenants/{other}/roles",
                json={"name": "Foreign", "permissions": ["read"]},
            )
            foreign = r.json()["id"]
            assert (
                await owner.post(
                    path + "/assignments", json={"member": member, "role_id": foreign}
                )
            ).status_code == 404
            assert (
                await owner.put(
                    f"/api/v1/tenants/{other}/roles/{rid}",
                    json={**updated, "version": 3},
                )
            ).status_code == 404
