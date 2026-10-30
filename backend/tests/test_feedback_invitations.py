"""Public feedback capabilities do not disclose invoices or bypass tenant controls."""

import json
import os
import uuid
from datetime import timedelta
import httpx
import pytest
from pydantic import ValidationError
from app.api.feedback_invitations import Invite, Response


def test_invitation_contracts():
    for value in (0, 31, True):
        with pytest.raises(ValidationError):
            Invite(invoice_number="INV", expires_days=value)
    for fields in [
        dict(token="short"),
        dict(rating=True),
        dict(rating=6),
        dict(comment="   "),
        dict(comment="x" * 2001),
    ]:
        with pytest.raises(ValidationError):
            Response(**(dict(token="A" * 43, rating=5, comment="Good") | fields))


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_feedback_links_lifecycle_isolation_retry_and_rate_limit():
    from app import config, db, security
    from app.main import app

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
        ) as staff, httpx.AsyncClient(
            transport=transport,
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as customer:
            assert (
                await staff.post(
                    "/api/auth/login",
                    json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
                )
            ).status_code == 200

            async def old(action, **kw):
                r = await staff.post("/api/workspace", json=dict(action=action, **kw))
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Feedback shop", currency="PKR"))["id"]
            other = (await old("tenant", name="Other shop", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"
            invitations = base + "/feedback/invitations"

            async def post(path, payload):
                r = await staff.post(base + path, json=payload)
                assert r.status_code in (200, 201), r.text
                return r.json()

            product = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="F-1",
                    name="Private purchase",
                    category="General",
                    price=1000,
                    cost=600,
                    initial=10,
                    reorder=0,
                )
            )["id"]
            await post("/tills", dict(opening_cash=0))

            async def sale():
                result = await old(
                    "checkout",
                    tenant=tenant,
                    request=uuid.uuid4().hex,
                    items=[dict(id=product, quantity=1)],
                    payment="cash",
                    expected=1000,
                    tendered=1000,
                    customer="Private Buyer",
                )
                async with db.pool.acquire() as conn:
                    return await conn.fetchval(
                        "SELECT invoice_number FROM sales WHERE id=$1", result["id"]
                    )

            invoice = await sale()

            async def issue(number=invoice):
                return await post(
                    "/feedback/invitations", dict(invoice_number=number, expires_days=7)
                )

            async def preview(token):
                return await customer.post(
                    "/api/public/feedback/preview", json=dict(token=token)
                )

            first = await issue()
            token = first["url"].split("#")[1]
            assert (
                first["url"].startswith(config.APP_ORIGIN + "/feedback#")
                and len(token) == 43
            )
            async with db.pool.acquire() as conn:
                record = await conn.fetchrow(
                    "SELECT * FROM feedback_invitations WHERE id=$1", first["id"]
                )
                assert record["token_hash"] == security.digest(token)
                assert token not in str(dict(record))
                assert token not in str(
                    await conn.fetch(
                        "SELECT details FROM audit WHERE tenant=$1", tenant
                    )
                )
            r = await preview(token)
            assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
            assert set(r.json()) == {"business_name", "expires", "submitted"}
            assert invoice not in r.text and "Private Buyer" not in r.text
            assert r.json()["business_name"] == "Feedback shop"
            assert not r.json()["submitted"]
            listed = (await staff.get(invitations)).json()
            assert token not in json.dumps(listed) and "token_hash" not in json.dumps(
                listed
            )
            assert listed["items"][0]["status"] == "active"
            assert (await customer.get(invitations)).status_code == 401
            assert (
                await staff.post(
                    f"/api/v1/tenants/{other}/feedback/invitations",
                    json=dict(invoice_number=invoice),
                )
            ).status_code == 404
            assert (
                await staff.post(
                    f'/api/v1/tenants/{other}/feedback/invitations/{first["id"]}/revoke',
                    json={},
                )
            ).status_code == 404
            assert (
                await staff.post(
                    invitations,
                    json=dict(invoice_number=invoice),
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            # Strict public origin validation cannot be bypassed by an arbitrary Authorization header.
            assert (
                await customer.post(
                    "/api/public/feedback/preview",
                    json=dict(token=token),
                    headers={
                        "Origin": "https://evil.example",
                        "Authorization": "Bearer ignored",
                    },
                )
            ).status_code == 403
            assert (await preview("Z" * 43)).status_code == 404
            replacement = await issue()
            replacement_token = replacement["url"].split("#")[1]
            assert (await preview(token)).status_code == 404
            for _ in range(2):
                assert (
                    await staff.post(
                        invitations + "/" + replacement["id"] + "/revoke", json={}
                    )
                ).status_code == 200
            assert (await preview(replacement_token)).status_code == 404
            third = await issue()
            token = third["url"].split("#")[1]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE feedback_invitations SET expires=now()-interval '1 second' WHERE id=$1",
                    third["id"],
                )
            assert (await preview(token)).status_code == 404
            link = await issue()
            token = link["url"].split("#")[1]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET status='suspended' WHERE id=$1", tenant
                )
            assert (await preview(token)).status_code == 404
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET status='active' WHERE id=$1", tenant
                )
            payload = dict(
                token=token,
                rating=4,
                comment="Helpful service — شکریہ <script>alert(1)</script>",
            )
            for _ in range(2):
                r = await customer.post("/api/public/feedback/submit", json=payload)
                assert r.status_code == 200 and r.json() == dict(submitted=True), r.text
            assert (
                await customer.post(
                    "/api/public/feedback/submit", json=payload | {"rating": 5}
                )
            ).status_code == 409
            assert (await preview(token)).json()["submitted"]
            assert (
                await staff.post(invitations, json=dict(invoice_number=invoice))
            ).status_code == 409
            assert (
                await staff.post(invitations + "/" + link["id"] + "/revoke", json={})
            ).status_code == 409
            feedback = (await staff.get(base + "/feedback")).json()
            assert feedback["total"] == 1
            entry = feedback["items"][0]
            assert (
                entry["source"] == "customer"
                and entry["invoice_number"] == invoice
                and entry["comment"] == payload["comment"]
            )
            # Staff resolution never alters the original customer response or enables a second one.
            r = await staff.put(
                base + "/feedback/" + entry["id"],
                json=dict(version=1, status="resolved", note="Reviewed"),
            )
            assert r.status_code == 200
            assert (await preview(token)).json()["submitted"]
            assert (
                await customer.post("/api/public/feedback/submit", json=payload)
            ).status_code == 200
            # Revocation and per-link limits survive failed attempts and are shared by clients.
            another = await issue(await sale())
            token2 = another["url"].split("#")[1]
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE feedback_invitations SET attempts=30,window_start=now() WHERE id=$1",
                    another["id"],
                )
            assert (await preview(token2)).status_code == 429
            assert (
                await customer.post(
                    "/api/public/feedback/submit",
                    json=dict(token=token2, rating=5, comment="Blocked"),
                )
            ).status_code == 429
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT attempts FROM feedback_invitations WHERE id=$1",
                        another["id"],
                    )
                    == 32
                )
                await conn.execute(
                    "UPDATE feedback_invitations SET window_start=now()-interval '2 minutes' WHERE id=$1",
                    another["id"],
                )
            assert (await preview(token2)).status_code == 200
            email = uuid.uuid4().hex + "@example.com"
            password = "StaffPassword2026!"
            await old(
                "member",
                tenant=tenant,
                email=email,
                name="Stock staff",
                password=password,
                role="Stock Manager",
            )
            await staff.post(
                "/api/auth/login", json=dict(email=email, password=password)
            )
            assert (await staff.get(invitations)).status_code == 403
            assert (
                await staff.post(invitations, json=dict(invoice_number=invoice))
            ).status_code == 403
            assert (
                await staff.post(invitations + "/" + another["id"] + "/revoke", json={})
            ).status_code == 403
