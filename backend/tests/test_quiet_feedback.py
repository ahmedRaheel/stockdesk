import os, uuid, json
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest, httpx
from pydantic import ValidationError
from app.api.alerts import Rule
from app.features.alerts import quiet_now
from app.api.feedback import Submit, Resolve


def test_quiet_hour_boundaries_and_feedback_contracts():
    zone = ZoneInfo("Asia/Karachi")
    rule = dict(quiet_start=22 * 60, quiet_end=2 * 60)
    for h, m, expected in [
        (21, 59, False),
        (22, 0, True),
        (0, 0, True),
        (1, 59, True),
        (2, 0, False),
    ]:
        assert quiet_now(rule, datetime(2026, 10, 26, h, m, tzinfo=zone)) is expected
    assert quiet_now(dict(quiet_start=0, quiet_end=1440), datetime.now(zone))
    assert not quiet_now({}, datetime.now(zone))
    for kw in [
        dict(quiet_start=5),
        dict(quiet_start=5, quiet_end=5),
        dict(quiet_start=-1, quiet_end=60),
        dict(quiet_start=True, quiet_end=10),
    ]:
        with pytest.raises(ValidationError):
            Rule(name="Bad", kind="low_stock", **kw)
    for rating in [0, 6, True, 1.5]:
        with pytest.raises(ValidationError):
            Submit(request="r", rating=rating, comment="Test")
    with pytest.raises(ValidationError):
        Resolve(version=1, status="resolved", note="  ")


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_quiet_hours_and_feedback_workflows(monkeypatch):
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
            from app.features import alerts as feature

            payload = dict(
                name="Quiet stock",
                kind="low_stock",
                product=product,
                quiet_start=0,
                quiet_end=1440,
                escalate_after_minutes=1,
            )
            r = await c.post(base + "/rules", json=payload)
            assert r.status_code == 201, r.text
            r = await c.post(base + "/evaluate", json={})
            assert r.status_code == 200, r.text
            assert r.json()["opened"] == 0 and r.json()["deferred"] == 1
            original = feature.quiet_now
            monkeypatch.setattr(feature, "quiet_now", lambda rule, now: False)
            assert (await c.post(base + "/evaluate", json={})).json()["opened"] == 1
            episode = (await c.get(base)).json()["items"][0]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE inventory_alerts SET opened=now()-interval '5 minutes' WHERE tenant=$1",
                    tenant,
                )
            monkeypatch.setattr(feature, "quiet_now", original)
            assert (await c.post(base + "/evaluate", json={})).json()["escalated"] == 0
            assert (await c.get(base)).json()["items"][0]["severity"] == "warning"
            await old(
                "movement",
                tenant=tenant,
                product=product,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=5,
                notes="Clear in quiet hours",
            )
            assert (await c.post(base + "/evaluate", json={})).json()["resolved"] == 1
            # Deferred conditions which clear never create an alert later.
            monkeypatch.setattr(feature, "quiet_now", lambda rule, now: False)
            assert (await c.post(base + "/evaluate", json={})).json()["opened"] == 0
            fb = f"/api/v1/tenants/{tenant}/feedback"
            sale = await old(
                "checkout",
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=[dict(id=product, quantity=1)],
                payment="cash",
                expected=1000,
                tendered=1000,
            )
            body = dict(
                request=uuid.uuid4().hex,
                rating=2,
                comment="Queue was slow",
                invoice_number=sale["invoice_number"],
            )
            r = await c.post(fb, json=body)
            assert r.status_code == 201, r.text
            fid = r.json()["id"]
            assert (await c.post(fb, json=body)).json()["id"] == fid
            assert (await c.post(fb, json={**body, "rating": 5})).status_code == 409
            assert (
                await c.post(f"/api/v1/tenants/{other}/feedback", json=body)
            ).status_code == 404
            assert (
                await c.post(
                    fb,
                    json={
                        **body,
                        "request": uuid.uuid4().hex,
                        "invoice_number": "MISSING",
                    },
                )
            ).status_code == 404
            r = (await c.get(fb)).json()
            assert (
                r["summary"]["total"] == 1
                and float(r["summary"]["average"]) == 2
                and r["summary"]["open"] == 1
            )
            assert r["items"][0]["invoice_number"] == sale["invoice_number"]
            resolution = dict(
                version=1, status="resolved", note="Added another cashier"
            )
            assert (await c.put(fb + "/" + fid, json=resolution)).status_code == 200
            assert (await c.put(fb + "/" + fid, json=resolution)).status_code == 409
            assert (await c.get(fb + "?status=open")).json()["total"] == 0
            assert (await c.get(fb + "?status=resolved")).json()["items"][0][
                "comment"
            ] == body["comment"]
            assert (
                await c.put(
                    fb + "/" + fid,
                    json=dict(version=2, status="open", note="Customer still waiting"),
                )
            ).status_code == 200
            assert (await c.get(fb + "?status=open")).json()["total"] == 1
            assert (await c.get(f"/api/v1/tenants/{other}/feedback")).json()[
                "total"
            ] == 0
            assert (
                await c.put(f"/api/v1/tenants/{other}/feedback/" + fid, json=resolution)
            ).status_code == 404
            email = uuid.uuid4().hex + "@example.com"
            await old(
                "member",
                tenant=tenant,
                email=email,
                name="Counter",
                role="Cashier",
                password="CashierPassword2026!",
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as staff:
                assert (
                    await staff.post(
                        "/api/auth/login",
                        json=dict(email=email, password="CashierPassword2026!"),
                    )
                ).status_code == 200
                assert (await staff.get(fb)).status_code == 403
                assert (await staff.post(fb, json=body)).status_code == 403
                assert (
                    await staff.put(fb + "/" + fid, json=resolution)
                ).status_code == 403
            assert (
                await c.post(
                    fb,
                    json={**body, "request": uuid.uuid4().hex},
                    headers={"Origin": "https://wrong.example"},
                )
            ).status_code == 403
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM audit WHERE tenant=$1 AND action='Customer feedback updated'",
                        tenant,
                    )
                    == 2
                )
