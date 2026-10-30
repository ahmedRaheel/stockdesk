import os
import uuid
from datetime import timedelta
import httpx
import pytest
from pydantic import ValidationError
from app.api.memberships import Plan, Enroll, Change


def test_membership_contracts():
    base = dict(code="GOLD", name="Gold", duration_days=30)
    for patch in [
        dict(duration_days=True),
        dict(duration_days=0),
        dict(duration_days=731),
        dict(code="lower case"),
        dict(name="   "),
    ]:
        with pytest.raises(ValidationError):
            Plan(**(base | patch))
    with pytest.raises(ValidationError):
        Change(request="r", version=True, action="renew", note="Test")


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_membership_lifecycle_overlap_freezing_and_access():
    from app import config, db
    from app.main import app
    from app.rules import business_date

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
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
        ) as cashier:

            async def post(path, body, status=200):
                r = await c.post(path, json=body)
                assert r.status_code == status, r.text
                return r.json()

            await post(
                "/api/auth/login",
                dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )
            tenant = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Membership store", currency="PKR"),
                )
            )["id"]
            foreign = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Other members", currency="PKR"),
                )
            )["id"]
            base = f"/api/v1/tenants/{tenant}"
            url = base + "/memberships"
            today = business_date()
            customer = (
                await post(base + "/customers", dict(name="Member customer"), 201)
            )["id"]
            email = uuid.uuid4().hex + "@example.com"
            password = "CashierPassword2026!"
            await post(
                "/api/workspace",
                dict(
                    action="member",
                    tenant=tenant,
                    email=email,
                    password=password,
                    name="Member cashier",
                    role="Cashier",
                ),
            )
            assert (
                await cashier.post(
                    "/api/auth/login", json=dict(email=email, password=password)
                )
            ).status_code == 200
            plan = dict(
                code="GOLD",
                name="Gold membership",
                duration_days=30,
                benefits="Priority service",
                active=True,
            )
            pid = (await post(url + "/plans", plan, 201))["id"]
            assert (await cashier.get(url + "/plans")).status_code == 403
            enroll = dict(
                request=uuid.uuid4().hex,
                customer=customer,
                plan=pid,
                plan_version=1,
                valid_from=str(today),
                note="Customer enrolled",
            )
            await post(
                url, {**enroll, "valid_from": str(today - timedelta(days=1))}, 400
            )
            await post(
                url, {**enroll, "valid_from": str(today + timedelta(days=367))}, 400
            )
            await post(f"/api/v1/tenants/{foreign}/memberships", enroll, 404)
            mid = (await post(url, enroll, 201))["id"]
            assert (await post(url, enroll, 201))["replayed"]
            await post(url, {**enroll, "note": "Changed"}, 409)
            await post(url, {**enroll, "request": uuid.uuid4().hex}, 409)
            assert (
                await cashier.post(url, json={**enroll, "request": uuid.uuid4().hex})
            ).status_code == 403
            listing = (await c.get(url)).json()
            m = listing["items"][0]
            assert m["number"] == "MEM-000001" and m["valid_until"] == str(
                today + timedelta(days=29)
            )
            assert listing["counts"] == {"active": 1}
            summary = (
                await cashier.get(base + f"/sale-customers/{customer}/membership")
            ).json()["membership"]
            assert (
                set(summary) == {"number", "plan_name", "benefits", "valid_until"}
                and summary["benefits"] == "Priority service"
            )
            # Changing the plan cannot rewrite an enrolled customer's terms.
            r = await c.put(
                url + "/plans/" + pid,
                json={
                    **plan,
                    "version": 1,
                    "name": "New Gold",
                    "duration_days": 60,
                    "benefits": "Different terms",
                },
            )
            assert r.status_code == 200, r.text
            await post(
                url,
                {
                    **enroll,
                    "request": uuid.uuid4().hex,
                    "valid_from": str(today + timedelta(days=30)),
                },
                409,
            )
            assert (
                await c.put(url + "/plans/" + pid, json={**plan, "version": 1})
            ).status_code == 409
            action = dict(
                request=uuid.uuid4().hex,
                version=1,
                action="renew",
                note="Renew original term",
            )
            assert (await post(url + f"/{mid}/actions", action))["version"] == 2
            assert (await post(url + f"/{mid}/actions", action))["replayed"]
            m = (await c.get(url)).json()["items"][0]
            assert (
                m["valid_until"] == str(today + timedelta(days=59))
                and m["plan_snapshot"]["name"] == "Gold membership"
            )
            await post(
                url + f"/{mid}/actions", {**action, "request": uuid.uuid4().hex}, 409
            )
            # A non-overlapping future plan can be scheduled, blocking renewals into it.
            scheduled = {
                **enroll,
                "request": uuid.uuid4().hex,
                "plan_version": 2,
                "valid_from": str(today + timedelta(days=60)),
            }
            future = (await post(url, scheduled, 201))["id"]
            assert (await c.get(url + "?state=scheduled")).json()["counts"][
                "scheduled"
            ] == 1
            await post(
                url + f"/{mid}/actions",
                {**action, "request": uuid.uuid4().hex, "version": 2},
                409,
            )
            cancel = dict(
                request=uuid.uuid4().hex,
                version=2,
                action="cancel",
                note="Customer opted out",
            )
            await post(url + f"/{mid}/actions", cancel)
            assert (
                await cashier.get(base + f"/sale-customers/{customer}/membership")
            ).json()["membership"] is None
            await post(
                url + f"/{mid}/actions",
                {**action, "request": uuid.uuid4().hex, "version": 3},
                409,
            )
            # Retirement prevents new enrollments/renewals, not already active contractual coverage.
            r = await c.put(
                url + "/plans/" + pid, json={**plan, "version": 2, "active": False}
            )
            assert r.status_code == 200, r.text
            await post(
                url + f"/{future}/actions", {**action, "request": uuid.uuid4().hex}, 409
            )
            assert (
                await c.get(f"/api/v1/tenants/{foreign}/memberships/{mid}/history")
            ).status_code == 404
            hist = (await c.get(url + f"/{mid}/history")).json()["items"]
            assert [h["kind"] for h in hist] == [
                "cancelled",
                "renewed",
                "enrolled",
            ] and hist[-1]["details"]["plan"]["benefits"] == "Priority service"
            assert "signature" not in hist[0]
            # Expiry is derived from the business date; an expired renewal starts today.
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE customer_memberships SET valid_from=$1,valid_until=$2 WHERE id=$3",
                    today - timedelta(days=70),
                    today - timedelta(days=11),
                    future,
                )
            assert (await c.get(url + "?state=expired")).json()["items"][0][
                "id"
            ] == future
            r = await c.put(url + "/plans/" + pid, json={**plan, "version": 3})
            assert r.status_code == 200
            await post(
                url + f"/{future}/actions", {**action, "request": uuid.uuid4().hex}
            )
            m = (await c.get(url + "?state=active")).json()["items"][0]
            assert m["valid_from"] == str(today) and m["valid_until"] == str(
                today + timedelta(days=59)
            )  # Frozen 60-day term.
            # Membership activity never posts customer money.
            assert (await c.get(base + f"/customers/{customer}/statement")).json()[
                "entries"
            ] == []
            r = await c.post(
                url + f"/{future}/actions",
                json={**cancel, "request": uuid.uuid4().hex},
                headers={"Origin": "https://evil.example"},
            )
            assert r.status_code == 403
            async with db.pool.acquire() as conn:
                with pytest.raises(Exception, match="Membership history is immutable"):
                    await conn.execute(
                        "DELETE FROM membership_events WHERE tenant=$1 AND membership=$2",
                        tenant,
                        mid,
                    )
                await conn.execute(
                    "UPDATE customers SET active=false WHERE id=$1", customer
                )
            assert (
                await cashier.get(base + f"/sale-customers/{customer}/membership")
            ).status_code == 404
            await post(
                url + f"/{future}/actions",
                {**action, "request": uuid.uuid4().hex, "version": 2},
                404,
            )
