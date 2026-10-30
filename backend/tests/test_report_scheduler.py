import os
import uuid
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from pydantic import ValidationError
from app.api.report_schedules import Schedule
from app.features.report_scheduler import next_slot


def test_schedule_dates_and_contracts():
    now = datetime(2026, 10, 29, 3, tzinfo=timezone.utc)  # Thursday 08:00 Karachi
    assert next_slot(now, "daily", 0, 8, 0).isoformat() == "2026-10-30T08:00:00+05:00"
    assert next_slot(now, "weekly", 3, 8, 0).isoformat() == "2026-11-05T08:00:00+05:00"
    assert next_slot(now, "weekly", 4, 8, 0).isoformat() == "2026-10-30T08:00:00+05:00"
    for patch in [
        dict(hour=24),
        dict(minute=-1),
        dict(weekday=True),
        dict(frequency="hourly"),
    ]:
        with pytest.raises(ValidationError):
            Schedule(
                **(
                    dict(
                        id="id",
                        version=0,
                        name="Daily",
                        view="view",
                        view_version=1,
                        frequency="daily",
                        hour=8,
                    )
                    | patch
                )
            )


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_schedule_snapshots_retries_access_and_retention(monkeypatch):
    from app import db, config
    from app.main import app
    from app.features import report_scheduler as worker

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    config.REPORT_WORKER_ENABLED = False
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as c, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as staff:

            async def post(path, body, status=200):
                r = await c.post(path, json=body)
                assert r.status_code == status, r.text
                return r.json()

            async def put(path, body, status=200):
                r = await c.put(path, json=body)
                assert r.status_code == status, r.text
                return r.json()

            await post(
                "/api/auth/login",
                dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )
            tenant = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Scheduled test", currency="PKR"),
                )
            )["id"]
            other = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Other scheduled", currency="PKR"),
                )
            )["id"]
            base = f"/api/v1/tenants/{tenant}"
            url = base + "/report-schedules"
            definition = dict(
                group="products", columns=["sku", "name", "net_sales"], days=7
            )
            view = dict(
                id=uuid.uuid4().hex,
                name="Weekly sales",
                version=0,
                definition=definition,
            )
            await put(base + "/report-builder/views", view)
            body = dict(
                id=uuid.uuid4().hex,
                version=0,
                name="Morning report",
                view=view["id"],
                view_version=1,
                frequency="daily",
                weekday=0,
                hour=8,
                minute=0,
                start_now=True,
                active=True,
            )
            await put(url, body)
            assert (await put(url, body))["replayed"]
            await put(url, {**body, "name": "Changed"}, 409)
            await put(f"/api/v1/tenants/{other}/report-schedules", body, 404)
            assert (await post(url + "/evaluate", {}))["outcomes"] == {"succeeded": 1}
            assert (await post(url + "/evaluate", {}))["outcomes"] == {}
            runs = (await c.get(url + "/runs")).json()["items"]
            assert len(runs) == 1 and runs[0]["attempts"] == 1
            rid = runs[0]["id"]
            snap = (await c.get(url + "/runs/" + rid)).json()
            assert (
                snap["status"] == "succeeded"
                and snap["result"]["columns"][0]["key"] == "sku"
            )
            assert (
                await c.get(f"/api/v1/tenants/{other}/report-schedules/runs/{rid}")
            ).status_code == 404
            await put(
                base + "/report-builder/views",
                {
                    **view,
                    "version": 1,
                    "definition": {**definition, "columns": ["cost"]},
                },
            )
            await post(
                base + "/products",
                dict(
                    sku="NEW", name="New item", category="General", price=100, initial=0
                ),
                201,
            )
            assert (await c.get(url + "/runs/" + rid)).json()["result"] == snap[
                "result"
            ]
            async with db.pool.acquire() as conn:
                with pytest.raises(
                    Exception, match="Successful report snapshots cannot be changed"
                ):
                    await conn.execute(
                        "UPDATE report_runs SET error='tampered' WHERE id=$1", rid
                    )
            # Pause / resume preserve frozen definition and require current versions.
            await post(
                url + "/" + body["id"] + "/activation", dict(version=1, active=False)
            )
            await post(
                url + "/" + body["id"] + "/activation",
                dict(version=1, active=True),
                409,
            )
            await post(
                url + "/" + body["id"] + "/activation", dict(version=2, active=True)
            )
            assert (await c.get(url)).json()["items"][0]["definition"][
                "columns"
            ] == definition["columns"]
            # New slot: fail twice, then succeed on the same run identity.
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE report_schedules SET next_run=now()-interval '1 day' WHERE id=$1",
                    body["id"],
                )
            original = worker.load_management_report

            async def failure(*args, **kwargs):
                raise RuntimeError("Private connection detail")

            monkeypatch.setattr(worker, "load_management_report", failure)
            assert (await worker.worker_once(tenant)) == {"retrying": 1}
            assert await worker.worker_once(tenant) == {}
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE report_schedules SET retry_after=now()-interval '1 second' WHERE id=$1",
                    body["id"],
                )
            assert await worker.worker_once(tenant) == {"retrying": 1}
            monkeypatch.setattr(worker, "load_management_report", original)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE report_schedules SET retry_after=now()-interval '1 second' WHERE id=$1",
                    body["id"],
                )
            assert await worker.worker_once(tenant) == {"succeeded": 1}
            runs = (await c.get(url + "/runs")).json()["items"]
            assert runs[0]["attempts"] == 3 and len(runs) == 2
            assert "Private connection detail" not in str(runs)
            # Three committed failures stop retrying and move to the next slot.
            monkeypatch.setattr(worker, "load_management_report", failure)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE report_schedules SET next_run=now()-interval '2 days',retry_after=NULL WHERE id=$1",
                    body["id"],
                )
            for expected in ["retrying", "retrying", "failed"]:
                assert await worker.worker_once(tenant) == {expected: 1}
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE report_schedules SET retry_after=now()-interval '1 second' WHERE id=$1",
                        body["id"],
                    )
            assert await worker.worker_once(tenant) == {}
            monkeypatch.setattr(worker, "load_management_report", original)
            # Editing cancels a pending retry and keeps prior attempts readable.
            monkeypatch.setattr(worker, "load_management_report", failure)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE report_schedules SET next_run=now()-interval '3 days',retry_after=NULL WHERE id=$1",
                    body["id"],
                )
            assert await worker.worker_once(tenant) == {"retrying": 1}
            await put(
                url, {**body, "version": 3, "view_version": 2, "start_now": False}
            )
            assert (await c.get(url + "/runs")).json()["items"][0][
                "status"
            ] == "cancelled"
            monkeypatch.setattr(worker, "load_management_report", original)
            # A new completed run prunes only old snapshots beyond the retention cap.
            async with db.pool.acquire() as conn:
                for index in range(31):
                    await conn.execute(
                        "INSERT INTO report_runs(id,tenant,schedule,scheduled_for,definition,status,attempts,error,created,schedule_name,owner_email) VALUES($1,$2,$3,now()-($4::int*interval '1 day'),'{}','failed',1,'Old fixture',now()-($4::int*interval '1 day'),'Old','test@example.com')",
                        uuid.uuid4().hex,
                        tenant,
                        body["id"],
                        40 + index,
                    )
                await conn.execute(
                    "UPDATE report_schedules SET next_run=now()-interval '5 days',retry_after=NULL WHERE id=$1",
                    body["id"],
                )
            assert await worker.worker_once(tenant) == {"succeeded": 1}
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM report_runs WHERE tenant=$1 AND schedule=$2",
                        tenant,
                        body["id"],
                    )
                    == 30
                )
            # Current role revocation pauses a due schedule before reading report data.
            email = uuid.uuid4().hex + "@example.com"
            password = "SchedulerPassword2026!"
            await post(
                "/api/workspace",
                dict(
                    action="member",
                    tenant=tenant,
                    email=email,
                    password=password,
                    name="Report manager",
                    role="Manager",
                ),
            )
            await staff.post(
                "/api/auth/login", json=dict(email=email, password=password)
            )
            managerbody = {**body, "id": uuid.uuid4().hex, "view_version": 2}
            r = await staff.put(url, json=managerbody)
            assert r.status_code == 200, r.text
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE members SET role='Cashier' WHERE tenant=$1 AND user_id=(SELECT id FROM users WHERE email=$2)",
                    tenant,
                    email,
                )
            assert await worker.worker_once(tenant) == {"failed": 1}
            schedules = (await c.get(url)).json()["items"]
            m = next(s for s in schedules if s["id"] == managerbody["id"])
            assert not m["active"]
            for path in [url, url + "/runs", url + "/runs/" + rid]:
                assert (await staff.get(path)).status_code == 403
            assert (await staff.post(url + "/evaluate", json={})).status_code == 403
            assert (
                await c.post(
                    url + "/evaluate",
                    json={},
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            # A fixed report end cannot be scheduled.
            await put(
                base + "/report-builder/views",
                {
                    **view,
                    "version": 2,
                    "definition": {**definition, "end": "2026-01-01"},
                },
            )
            await put(url, {**body, "id": uuid.uuid4().hex, "view_version": 3}, 400)
            # Changing a schedule cancels its pending retry; suspended tenants do no work.
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET status='suspended' WHERE id=$1", tenant
                )
                await conn.execute(
                    "UPDATE report_schedules SET next_run=now()-interval '1 day',retry_after=NULL WHERE id=$1",
                    body["id"],
                )
            assert await worker.worker_once(tenant) == {}
