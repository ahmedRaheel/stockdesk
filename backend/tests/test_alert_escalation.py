import os, uuid, json
import pytest, httpx
from pydantic import ValidationError
from app.api.alerts import Rule


def test_escalation_contract():
    assert Rule(name="Low", kind="low_stock").escalate_after_minutes is None
    for value in [0, -1, 10081, 1.5, True, "1"]:
        with pytest.raises(ValidationError):
            Rule(name="Low", kind="low_stock", escalate_after_minutes=value)
    with pytest.raises(ValidationError):
        Rule(
            name="Low", kind="low_stock", severity="critical", escalate_after_minutes=1
        )
    assert Rule(
        name="Low", kind="low_stock", severity="info", escalate_after_minutes=10080
    )


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_alert_escalation_due_acknowledgement_resolution_and_history():
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
            payload = dict(
                name="Escalate low inventory",
                kind="low_stock",
                product=product,
                severity="info",
                escalate_after_minutes=5,
            )
            r = await c.post(base + "/rules", json=payload)
            assert r.status_code == 201, r.text
            rid = r.json()["id"]
            assert (await c.get(base + "/rules")).json()["items"][0][
                "escalate_after_minutes"
            ] == 5

            async def evaluate():
                r = await c.post(base + "/evaluate", json={})
                assert r.status_code == 200, r.text
                return r.json()

            async def inbox(status="all", escalated=False):
                r = await c.get(
                    base,
                    params=dict(status=status, escalated_only=str(escalated).lower()),
                )
                assert r.status_code == 200, r.text
                return r.json()["items"]

            first = await evaluate()
            assert first["opened"] == 1 and first["escalated"] == 0
            eid = (await inbox())[0]["id"]

            async def age(minutes):
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE inventory_alerts SET opened=now()-($3::integer*interval '1 minute') WHERE tenant=$1 AND id=$2",
                        tenant,
                        eid,
                        minutes,
                    )

            await age(4)
            assert (await evaluate())["escalated"] == 0
            assert not await inbox(escalated=True)
            await age(5)
            assert (await evaluate())["escalated"] == 1
            episode = (await inbox(escalated=True))[0]
            assert (
                episode["severity"] == "critical"
                and episode["escalated_from"] == "info"
            )
            assert (
                episode["escalation_minutes"] == 5
                and episode["escalated_at"]
                and episode["id"] == eid
            )
            assert (await evaluate())["escalated"] == 0
            assert (await inbox(escalated=True))[0]["escalated_at"] == episode[
                "escalated_at"
            ]
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM audit WHERE tenant=$1 AND action='Inventory alerts escalated'",
                        tenant,
                    )
                    == 1
                )
            assert (
                await c.get(
                    f"/api/v1/tenants/{other}/alert-center?status=all&escalated_only=true"
                )
            ).json()["total"] == 0
            assert (
                await c.post(
                    base + f"/{eid}/acknowledge", json=dict(note="Ordering stock")
                )
            ).status_code == 200
            assert (await evaluate())["escalated"] == 0
            assert (await inbox("acknowledged", True))[0]["id"] == eid
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=5,
                notes="Replenish",
            )
            assert (await evaluate())["resolved"] == 1
            assert (await inbox("resolved", True))[0]["escalated_at"] == episode[
                "escalated_at"
            ]
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="OUT",
                quantity=5,
                notes="Stock used",
            )
            assert (await evaluate())["opened"] == 1
            eid = (await inbox("open"))[0]["id"]
            assert eid != episode["id"]
            assert (await inbox("open"))[0]["severity"] == "info"
            # Acknowledgement before the deadline suppresses escalation.
            assert (
                await c.post(
                    base + f"/{eid}/acknowledge", json=dict(note="Investigating")
                )
            ).status_code == 200
            await age(20)
            assert (await evaluate())["escalated"] == 0
            # Editing starts a new episode with new configuration.
            changed = {
                **payload,
                "severity": "warning",
                "escalate_after_minutes": 1,
                "version": 1,
            }
            assert (
                await c.put(base + "/rules/" + rid, json=changed)
            ).status_code == 200
            assert (
                await c.put(base + "/rules/" + rid, json=changed)
            ).status_code == 409
            await evaluate()
            eid = (await inbox("open"))[0]["id"]
            await age(2)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE inventory_alert_rules SET last_evaluated=NULL WHERE tenant=$1",
                    tenant,
                )
            await worker_once()
            assert (await inbox("open", True))[0]["escalated_from"] == "warning"
            # Cleared conditions resolve before overdue escalation.
            assert (
                await c.put(base + "/rules/" + rid, json={**changed, "version": 2})
            ).status_code == 200
            await evaluate()
            eid = (await inbox("open"))[0]["id"]
            await age(2)
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=5,
                notes="Clear before evaluation",
            )
            result = await evaluate()
            assert result["resolved"] == 1 and result["escalated"] == 0
            # Disabling escalation persists and does not alter historical episodes.
            assert (
                await c.put(
                    base + "/rules/" + rid,
                    json={**payload, "version": 3, "escalate_after_minutes": None},
                )
            ).status_code == 200
            assert (await c.get(base + "/rules")).json()["items"][0][
                "escalate_after_minutes"
            ] is None
            assert len(await inbox("resolved", True)) == 2
