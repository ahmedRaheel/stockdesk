"""Recovery cases are permissioned workflow records, never financial postings."""

import os
import uuid
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from pydantic import ValidationError
from app.api.recovery_tracking import Create, Activity


def test_recovery_contracts():
    body = dict(
        request="r",
        receivable="i",
        assigned_to="a",
        note="Follow up",
        next_follow_up="2026-10-29T10:00:00+05:00",
    )
    for change in [
        dict(next_follow_up="2026-10-29T10:00:00"),
        dict(note="  "),
        dict(note="x" * 2001),
    ]:
        with pytest.raises(ValidationError):
            Create(**(body | change))
    activity = dict(
        request="r",
        version=1,
        outcome="promise",
        note="Called",
        next_follow_up=body["next_follow_up"],
        promised_on="2026-10-30",
        promised_amount=100,
    )
    for change in [
        dict(promised_amount=True),
        dict(promised_on=None),
        dict(promised_amount=0),
        dict(outcome="note"),
        dict(version=True),
    ]:
        with pytest.raises(ValidationError):
            Activity(**(activity | change))


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_recovery_lifecycle_permissions_replay_and_balances():
    from app import config, db
    from app.main import app
    from app.rules import business_date

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
        ) as agent, httpx.AsyncClient(
            transport=transport,
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as other_agent:

            async def post(client, path, payload, status=200):
                r = await client.post(path, json=payload)
                assert r.status_code == status, r.text
                return r.json()

            async def legacy(**kw):
                return await post(owner, "/api/workspace", kw)

            await post(
                owner,
                "/api/auth/login",
                dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )
            tenant = (
                await legacy(action="tenant", name="Recovery workflow", currency="PKR")
            )["id"]
            foreign = (
                await legacy(action="tenant", name="Other recovery", currency="PKR")
            )["id"]
            base = f"/api/v1/tenants/{tenant}"
            url = base + "/recovery-cases"
            ids = []
            for client, name, role in [
                (agent, "Agent A", "Cashier"),
                (other_agent, "Agent B", "Cashier"),
            ]:
                email = uuid.uuid4().hex + "@example.com"
                password = "RecoveryAgentPassword2026!"
                await legacy(
                    action="member",
                    tenant=tenant,
                    email=email,
                    name=name,
                    password=password,
                    role=role,
                )
                await post(
                    client, "/api/auth/login", dict(email=email, password=password)
                )
                async with db.pool.acquire() as c:
                    ids.append(
                        await c.fetchval("SELECT id FROM users WHERE email=$1", email)
                    )
            a, b = ids
            person = (
                await post(
                    owner,
                    base + "/customers",
                    dict(name="Credit customer", phone="03000000000"),
                    201,
                )
            )["id"]
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE customers SET credit_enabled=true,credit_limit=100000 WHERE tenant=$1 AND id=$2",
                    tenant,
                    person,
                )
            product = (
                await legacy(
                    action="product",
                    tenant=tenant,
                    sku="REC-1",
                    name="Item",
                    category="General",
                    price=10000,
                    cost=5000,
                    initial=10,
                    reorder=0,
                )
            )["id"]
            cash = next(
                x["id"]
                for x in (
                    await owner.get(base + "/lookups?kind=payment_method")
                ).json()["items"]
                if x["code"] == "cash"
            )
            await post(owner, base + "/tills", dict(opening_cash=0))

            async def sale():
                await post(
                    owner,
                    base + "/sales",
                    dict(
                        request=uuid.uuid4().hex,
                        items=[dict(id=product, quantity=1)],
                        payment="cash",
                        payment_method_id=cash,
                        customer_id=person,
                        paid_now=0,
                        due_date=str(business_date()),
                        expected=10000,
                        tendered=0,
                    ),
                )
                return (
                    await owner.get(base + f"/customers/{person}/statement")
                ).json()["documents"]

            docs = await sale()
            invoice = docs[0]["id"]
            now = datetime.now(timezone.utc)
            past = (now - timedelta(minutes=2)).isoformat()
            future = (now + timedelta(days=2)).isoformat()
            payload = dict(
                request=uuid.uuid4().hex,
                receivable=invoice,
                assigned_to=a,
                next_follow_up=past,
                note="Contact customer about invoice",
            )
            await post(agent, url, payload, 403)
            assert (await agent.get(url + "/agents")).status_code == 403
            eligible = (await owner.get(url + "/agents")).json()["items"]
            assert {a, b}.issubset({x["id"] for x in eligible})
            created = await post(owner, url, payload, 201)
            case = created["id"]
            assert (await post(owner, url, payload, 201))["replayed"]
            await post(owner, url, {**payload, "note": "Different"}, 409)
            await post(owner, url, {**payload, "request": uuid.uuid4().hex}, 409)
            assert (
                await owner.get(
                    f"/api/v1/tenants/{foreign}/recovery-cases/{case}/history"
                )
            ).status_code == 404
            await post(
                owner,
                f"/api/v1/tenants/{foreign}/recovery-cases",
                {**payload, "request": uuid.uuid4().hex},
                400,
            )  # Foreign agent unavailable.
            listing = (await agent.get(url + "?mine=true")).json()
            assert (
                listing["counts"]["due"] == 1
                and listing["items"][0]["balance"] == 10000
                and not listing["can_manage"]
            )
            assert (await other_agent.get(url + "?mine=true")).json()["items"] == []
            activity = dict(
                request=uuid.uuid4().hex,
                version=1,
                outcome="no_answer",
                note="No response; retry tomorrow",
                next_follow_up=future,
            )
            await post(other_agent, url + f"/{case}/activities", activity, 403)
            result = await post(agent, url + f"/{case}/activities", activity)
            assert result["version"] == 2
            assert (await post(agent, url + f"/{case}/activities", activity))[
                "replayed"
            ]
            assert (await owner.get(url)).json()["items"] == []
            assert (await owner.get(url + "?state=upcoming")).json()["items"][0][
                "version"
            ] == 2
            await post(
                agent,
                url + f"/{case}/activities",
                {**activity, "request": uuid.uuid4().hex},
                409,
            )
            promise = {
                **activity,
                "request": uuid.uuid4().hex,
                "version": 2,
                "outcome": "promise",
                "promised_on": str(business_date() + timedelta(days=1)),
                "promised_amount": 10001,
            }
            await post(agent, url + f"/{case}/activities", promise, 400)
            promise["promised_amount"] = 5000
            await post(
                agent,
                url + f"/{case}/activities",
                {**promise, "promised_on": str(business_date() - timedelta(days=1))},
                400,
            )
            assert (await post(agent, url + f"/{case}/activities", promise))[
                "version"
            ] == 3
            statement = (
                await owner.get(base + f"/customers/{person}/statement")
            ).json()
            assert (
                statement["balance"] == 10000 and statement["payments"] == []
            )  # Promise is not payment.
            hist = (await agent.get(url + f"/{case}/history")).json()["items"]
            assert len(hist) == 3 and hist[0]["details"]["promised_amount"] == 5000
            assert "signature" not in hist[0] and "request" not in hist[0]
            update = dict(
                request=uuid.uuid4().hex,
                version=3,
                assigned_to=b,
                next_follow_up=past,
                status="open",
                note="Reassign to another agent",
            )
            assert (await agent.put(url + f"/{case}", json=update)).status_code == 403
            r = await owner.put(url + f"/{case}", json=update)
            assert r.status_code == 200, r.text
            assert (await owner.put(url + f"/{case}", json=update)).json()["replayed"]
            await post(
                agent,
                url + f"/{case}/activities",
                {**activity, "request": uuid.uuid4().hex, "version": 4},
                403,
            )
            assert (await agent.get(url + "?mine=true")).json()["items"] == []
            # Losing access takes effect immediately. A manager can reassign or close the case.
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE members SET active=false WHERE tenant=$1 AND user_id=$2",
                    tenant,
                    b,
                )
            assert b not in {
                x["id"] for x in (await owner.get(url + "/agents")).json()["items"]
            }
            await post(
                other_agent,
                url + f"/{case}/activities",
                {**activity, "request": uuid.uuid4().hex, "version": 4},
                403,
            )
            r = await owner.put(
                url + f"/{case}",
                json={**update, "request": uuid.uuid4().hex, "version": 4},
            )
            assert r.status_code == 400
            close = {
                **update,
                "request": uuid.uuid4().hex,
                "version": 4,
                "status": "closed",
                "note": "Closed after review",
            }
            r = await owner.put(url + f"/{case}", json=close)
            assert r.status_code == 200, r.text
            assert (await owner.get(url + "?state=closed")).json()["counts"][
                "closed"
            ] == 1
            assert (await owner.get(base + f"/customers/{person}/statement")).json()[
                "balance"
            ] == 10000
            reopen = {
                **update,
                "request": uuid.uuid4().hex,
                "version": 5,
                "assigned_to": a,
                "note": "Reopen for follow-up",
            }
            r = await owner.put(url + f"/{case}", json=reopen)
            assert r.status_code == 200, r.text
            # Actual payment updates the live queue without fake recovery attribution.
            payment = dict(
                request=uuid.uuid4().hex,
                customer=person,
                amount=4000,
                method=cash,
                reference="Partial",
            )
            await post(owner, base + "/recoveries", payment)
            assert (await owner.get(url)).json()["items"][0]["balance"] == 6000
            await post(
                owner,
                base + "/recoveries",
                {**payment, "request": uuid.uuid4().hex, "amount": 6000},
            )
            assert (await owner.get(url)).json()["items"] == []
            assert (await owner.get(url + "?state=settled")).json()["items"][0][
                "balance"
            ] == 0
            await post(
                agent,
                url + f"/{case}/activities",
                {**activity, "request": uuid.uuid4().hex, "version": 6},
                409,
            )
            assert (
                await owner.put(
                    url + f"/{case}",
                    json={**reopen, "request": uuid.uuid4().hex, "version": 6},
                )
            ).status_code == 409
            # Due scheduling derives from database time, not a client clock or job.
            docs = await sale()
            second = next(x["id"] for x in docs if x["balance"] > 0)
            upcoming = await post(
                owner,
                url,
                {
                    **payload,
                    "request": uuid.uuid4().hex,
                    "receivable": second,
                    "next_follow_up": future,
                },
                201,
            )
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE recovery_cases SET next_follow_up=now()-interval '1 minute' WHERE id=$1",
                    upcoming["id"],
                )
            assert (await agent.get(url + "?mine=true")).json()["counts"]["due"] == 1
            # CSRF and invalid schedules leave no history or version changes.
            r = await owner.put(
                url + f"/{case}", json=close, headers={"Origin": "https://evil.example"}
            )
            assert r.status_code == 403
            await post(
                agent,
                url + f"/{upcoming['id']}/activities",
                {
                    **activity,
                    "request": uuid.uuid4().hex,
                    "version": 1,
                    "next_follow_up": (now + timedelta(days=400)).isoformat(),
                },
                400,
            )
            assert (
                len(
                    (await owner.get(url + f"/{upcoming['id']}/history")).json()[
                        "items"
                    ]
                )
                == 1
            )
            async with db.pool.acquire() as c:
                with pytest.raises(Exception, match="Recovery history is immutable"):
                    await c.execute(
                        "DELETE FROM recovery_events WHERE tenant=$1 AND case_id=$2",
                        tenant,
                        case,
                    )
            # A user without credit access cannot read notes or list cases.
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE members SET role='Stock Manager' WHERE tenant=$1 AND user_id=$2",
                    tenant,
                    a,
                )
            assert (await agent.get(url)).status_code == 403
            assert (await agent.get(url + f"/{case}/history")).status_code == 403

            # Custom grants, rather than the built-in role label, decide eligibility.
            role_id = uuid.uuid4().hex
            async with db.pool.acquire() as c:
                await c.execute(
                    "INSERT INTO tenant_roles(id,tenant,name) VALUES($1,$2,'Recovery agent')",
                    role_id,
                    tenant,
                )
                await c.execute(
                    "INSERT INTO tenant_role_permissions(tenant,role_id,permission) VALUES($1,$2,'credit')",
                    tenant,
                    role_id,
                )
                await c.execute(
                    "UPDATE members SET custom_role_id=$1 WHERE tenant=$2 AND user_id=$3",
                    role_id,
                    tenant,
                    a,
                )
            assert a in {
                x["id"] for x in (await owner.get(url + "/agents")).json()["items"]
            }
            assert (await agent.get(url)).status_code == 200
            async with db.pool.acquire() as c:
                await c.execute(
                    "UPDATE tenant_roles SET active=false WHERE tenant=$1 AND id=$2",
                    tenant,
                    role_id,
                )
            assert a not in {
                x["id"] for x in (await owner.get(url + "/agents")).json()["items"]
            }
            current = (await owner.get(url)).json()["items"][0]
            assert current["agent_available"] is False
            assert (await agent.get(url)).status_code == 403
