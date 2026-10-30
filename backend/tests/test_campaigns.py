import os
import uuid
import httpx
import pytest
from pydantic import ValidationError
from app.api.campaigns import Create, Contact


def test_campaign_contracts():
    with pytest.raises(ValidationError):
        Create(
            request="x",
            name=" ",
            message="Hello",
            audience="all",
            audience_token="a" * 64,
        )
    for patch in [
        dict(version=True),
        dict(outcome="pending"),
        dict(note=" "),
        dict(version=0),
    ]:
        with pytest.raises(ValidationError):
            Contact(
                **(
                    dict(request="x", version=1, outcome="contacted", note="Talked")
                    | patch
                )
            )


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_campaign_lifecycle_suppression_retry_and_access():
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
                    dict(action="tenant", name="Campaign test", currency="PKR"),
                )
            )["id"]
            other = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Other campaign", currency="PKR"),
                )
            )["id"]
            base = f"/api/v1/tenants/{tenant}"
            url = base + "/campaigns"
            person = (
                await post(
                    base + "/customers",
                    dict(name="First customer", phone="03000000000"),
                    201,
                )
            )["id"]
            preview = await post(url + "/preview", dict(audience="all"))
            assert preview["count"] == 1
            body = dict(
                request=uuid.uuid4().hex,
                name="Spring care",
                message="Service follow-up",
                audience="all",
                audience_token=preview["audience_token"],
            )
            second = (
                await post(base + "/customers", dict(name="Second customer"), 201)
            )["id"]
            await post(url, body, 409)
            body["audience_token"] = (
                await post(url + "/preview", dict(audience="all"))
            )["audience_token"]
            cid = (await post(url, body, 201))["id"]
            assert (await post(url, body, 201))["replayed"]
            await post(url, {**body, "message": "Changed"}, 409)
            later = (await post(base + "/customers", dict(name="Later customer"), 201))[
                "id"
            ]
            detail = (await c.get(url + "/" + cid)).json()
            assert len(detail["items"]) == 2 and detail["counts"] == {"pending": 2}
            assert later not in [r["customer"] for r in detail["items"]]
            action = dict(
                request=uuid.uuid4().hex, version=1, action="completed", note="Finished"
            )
            await post(url + "/" + cid + "/actions", action, 409)
            contact = dict(
                request=uuid.uuid4().hex,
                version=1,
                outcome="opted_out",
                note="Customer requested no further campaign contact",
            )
            await post(url + "/" + cid + "/recipients/" + person, contact)
            assert (await post(url + "/" + cid + "/recipients/" + person, contact))[
                "replayed"
            ]
            await post(url + "/" + cid + "/recipients/" + second, contact, 409)
            await post(
                url + "/" + cid + "/recipients/" + person,
                {
                    **contact,
                    "request": uuid.uuid4().hex,
                    "version": 2,
                    "outcome": "contacted",
                },
                409,
            )
            await post(
                url + "/" + cid + "/recipients/" + person,
                {**contact, "request": uuid.uuid4().hex, "outcome": "skipped"},
                409,
            )
            pre = await post(url + "/preview", dict(audience="all"))
            assert pre["count"] == 2 and person not in [r["id"] for r in pre["sample"]]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE customers SET active=false WHERE id=$1", second
                )
            nextcontact = {
                **contact,
                "request": uuid.uuid4().hex,
                "outcome": "contacted",
            }
            await post(url + "/" + cid + "/recipients/" + second, nextcontact, 409)
            nextcontact["outcome"] = "skipped"
            await post(url + "/" + cid + "/recipients/" + second, nextcontact)
            await post(url + "/" + cid + "/actions", action)
            assert (await post(url + "/" + cid + "/actions", action))["replayed"]
            await post(
                url + "/" + cid + "/recipients/" + person,
                {
                    **contact,
                    "request": uuid.uuid4().hex,
                    "version": 2,
                    "outcome": "skipped",
                },
                409,
            )
            assert (await c.get(url + "/" + cid)).json()["campaign"][
                "status"
            ] == "completed"
            hist = (await c.get(url + "/" + cid + "/history")).json()["items"]
            assert len(hist) == 4 and all("signature" not in h for h in hist)
            assert (
                await c.get(f"/api/v1/tenants/{other}/campaigns/{cid}")
            ).status_code == 404
            assert (
                await c.get(f"/api/v1/tenants/{other}/campaigns/{cid}/history")
            ).status_code == 404
            assert (
                await c.post(
                    url + "/preview",
                    json={"audience": "all"},
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            email = uuid.uuid4().hex + "@example.com"
            password = "CashierPassword2026!"
            await post(
                "/api/workspace",
                dict(
                    action="member",
                    tenant=tenant,
                    email=email,
                    password=password,
                    name="Campaign cashier",
                    role="Cashier",
                ),
            )
            assert (
                await cashier.post(
                    "/api/auth/login", json=dict(email=email, password=password)
                )
            ).status_code == 200
            for path in [url, url + "/" + cid, url + "/" + cid + "/history"]:
                assert (await cashier.get(path)).status_code == 403
            assert (await cashier.post(url, json=body)).status_code == 403
            assert (
                await cashier.post(url + "/preview", json={"audience": "all"})
            ).status_code == 403
            # Membership audience is current and active, not merely enrolled at some point.
            assert (await post(url + "/preview", dict(audience="members")))[
                "count"
            ] == 0
            plan = (
                await post(
                    base + "/memberships/plans",
                    dict(code="CARE", name="Care", duration_days=30),
                    201,
                )
            )["id"]
            await post(
                base + "/memberships",
                dict(
                    request=uuid.uuid4().hex,
                    customer=later,
                    plan=plan,
                    plan_version=1,
                    valid_from=str(business_date()),
                    note="Join",
                ),
                201,
            )
            pre = await post(url + "/preview", dict(audience="members"))
            assert pre["count"] == 1 and pre["sample"][0]["id"] == later
            memberbody = {
                **body,
                "request": uuid.uuid4().hex,
                "audience": "members",
                "audience_token": pre["audience_token"],
            }
            nextid = (await post(url, memberbody, 201))["id"]
            await post(
                url + "/" + nextid + "/actions",
                {**action, "request": uuid.uuid4().hex, "action": "cancelled"},
            )
            assert (await c.get(url + "/" + nextid)).json()["campaign"][
                "status"
            ] == "cancelled"
            async with db.pool.acquire() as conn:
                with pytest.raises(Exception, match="Campaign history is immutable"):
                    await conn.execute(
                        "DELETE FROM campaign_events WHERE tenant=$1", tenant
                    )
            assert (await c.get(base + f"/customers/{person}/statement")).json()[
                "entries"
            ] == []
