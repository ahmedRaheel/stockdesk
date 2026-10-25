import os, uuid, json
from datetime import timedelta
import pytest, httpx
from pydantic import ValidationError
from app.api.alerts import Rule


def test_alert_rule_contracts():
    assert Rule(name="Low", kind="low_stock").threshold is None
    assert Rule(name="Expiry", kind="expiry", expiry_days=0).expiry_days == 0
    for payload in [
        dict(name="Bad", kind="expiry", threshold=1),
        dict(name="Bad", kind="low_stock", threshold=-1),
        dict(name="Bad", kind="expiry", expiry_days=366),
    ]:
        with pytest.raises(ValidationError):
            Rule(**payload)


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_alert_lifecycle_rules_worker_tenant_permissions_and_recurrence():
    from app import config, db
    from app.main import app
    from app.rules import business_date
    from app.features.alerts import worker_once

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

            async def old(action, **kw):
                r = await c.post("/api/workspace", json=dict(action=action, **kw))
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Alert tests", currency="PKR"))["id"]
            other = (await old("tenant", name="Other alert tests", currency="PKR"))[
                "id"
            ]
            base = f"/api/v1/tenants/{tenant}/alert-center"
            product = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="LOW",
                    name="Low stock item",
                    category="General",
                    price=1000,
                    cost=600,
                    initial=1,
                    reorder=2,
                )
            )["id"]
            empty = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="EMPTY",
                    name="Out of stock",
                    category="General",
                    price=1000,
                    cost=600,
                    initial=0,
                    reorder=0,
                )
            )["id"]
            payload = dict(name="Low inventory", kind="low_stock", product=product)
            r = await c.post(base + "/rules", json=payload)
            assert r.status_code == 201, r.text
            rule = r.json()["id"]
            assert (await c.post(base + "/rules", json=payload)).status_code == 409
            assert (
                await c.post(
                    f"/api/v1/tenants/{other}/alert-center/rules", json=payload
                )
            ).status_code == 404

            async def evaluate():
                r = await c.post(base + "/evaluate", json={})
                assert r.status_code == 200, r.text
                return r.json()

            async def inbox(status="open"):
                r = await c.get(base, params=dict(status=status))
                assert r.status_code == 200, r.text
                return r.json()["items"]

            assert (await evaluate())["opened"] == 1
            first = (await inbox())[0]
            eid = first["id"]
            d = first["details"]
            d = json.loads(d) if isinstance(d, str) else d
            assert d["stock"] == "1.000" and d["threshold"] == "2.000"
            assert (await evaluate())["opened"] == 0
            assert (
                await c.post(
                    base + f"/{eid}/acknowledge", json=dict(note="Purchasing stock")
                )
            ).status_code == 200
            assert (
                await c.post(base + f"/{eid}/acknowledge", json=dict(note="Retry"))
            ).status_code == 200
            assert (await evaluate())["opened"] == 0
            assert (await inbox("acknowledged"))[0][
                "acknowledgement_note"
            ] == "Purchasing stock"
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=5,
                notes="Replenished",
            )
            assert (await evaluate())["resolved"] == 1
            assert (
                await c.post(base + f"/{eid}/acknowledge", json=dict(note="Too late"))
            ).status_code == 409
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="OUT",
                quantity=5,
                notes="Adjustment",
            )
            assert (await evaluate())["opened"] == 1
            assert (await inbox())[0]["id"] != eid
            updated = {**payload, "version": 1, "active": False}
            assert (
                await c.put(base + f"/rules/{rule}", json=updated)
            ).status_code == 200
            assert (
                await c.put(base + f"/rules/{rule}", json=updated)
            ).status_code == 409
            assert not await inbox()
            assert (await evaluate())["evaluated"] == 0
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE stock_batches SET expires=$1 WHERE tenant=$2 AND product=$3",
                    business_date() + timedelta(days=3),
                    tenant,
                    product,
                )
            expiry = (
                await c.post(
                    base + "/rules",
                    json=dict(
                        name="Expiry",
                        kind="expiry",
                        product=product,
                        expiry_days=3,
                        severity="critical",
                    ),
                )
            ).json()["id"]
            assert (await evaluate())["opened"] == 1
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE stock_batches SET expires=$1 WHERE tenant=$2 AND product=$3",
                    business_date() + timedelta(days=4),
                    tenant,
                    product,
                )
            assert (await evaluate())["resolved"] == 1
            assert (
                await c.post(
                    base + "/rules",
                    json=dict(name="Stock out", kind="stock_out", product=empty),
                )
            ).status_code == 201
            await worker_once()
            assert len(await inbox()) == 1 and (await inbox())[0]["kind"] == "stock_out"
            async with db.pool.acquire() as conn:
                before = await conn.fetchval(
                    "SELECT max(last_evaluated) FROM inventory_alert_rules WHERE tenant=$1",
                    tenant,
                )
            await worker_once()
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT max(last_evaluated) FROM inventory_alert_rules WHERE tenant=$1",
                        tenant,
                    )
                    == before
                )
            # Suspended tenants are not evaluated by the system worker.
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE inventory_alert_rules SET last_evaluated=NULL WHERE tenant=$1",
                    tenant,
                )
                await conn.execute(
                    "UPDATE tenants SET status='suspended' WHERE id=$1", tenant
                )
            await worker_once()
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT max(last_evaluated) FROM inventory_alert_rules WHERE tenant=$1",
                        tenant,
                    )
                    is None
                )
                await conn.execute(
                    "UPDATE tenants SET status='active' WHERE id=$1", tenant
                )
                await conn.execute(
                    "UPDATE products SET active=false WHERE tenant=$1 AND id=$2",
                    tenant,
                    empty,
                )
            assert (await evaluate())["resolved"] == 1
            assert (await c.get(f"/api/v1/tenants/{other}/alert-center")).json()[
                "items"
            ] == []
            assert (
                await c.post(
                    f"/api/v1/tenants/{other}/alert-center/{eid}/acknowledge",
                    json=dict(note="No"),
                )
            ).status_code == 404
            assert (await c.get(base + "?limit=101")).status_code == 422
            email = uuid.uuid4().hex + "@example.com"
            password = "CashierPassword2026!"
            await old(
                "member",
                tenant=tenant,
                email=email,
                name="Cashier",
                password=password,
                role="Cashier",
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as staff:
                await staff.post(
                    "/api/auth/login", json=dict(email=email, password=password)
                )
                for path in [base, base + "/rules"]:
                    assert (await staff.get(path)).status_code == 403
                assert (
                    await staff.post(base + "/evaluate", json={})
                ).status_code == 403
                assert (
                    await staff.post(base + "/rules", json=payload)
                ).status_code == 403
                assert (
                    await staff.post(base + f"/{eid}/acknowledge", json=dict(note="No"))
                ).status_code == 403
            assert (
                await c.post(
                    base + "/evaluate",
                    json={},
                    headers={"Origin": "http://evil.invalid"},
                )
            ).status_code == 403
