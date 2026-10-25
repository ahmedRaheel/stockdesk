"""Partial corrections keep original evidence, exact money and stock/till invariants."""

import os
import uuid
from decimal import Decimal
import httpx
import pytest


def test_proportional_returns():
    from app.api.exchanges import proportional, ReturnedLine
    from pydantic import ValidationError

    assert proportional(101, Decimal(2), Decimal(3)) == 67
    assert proportional(101, Decimal(1), Decimal(3)) == 34
    assert proportional(101, Decimal(0), Decimal(3)) == 0
    with pytest.raises(ValidationError):
        ReturnedLine(item="x", quantity=0, reason="damaged")


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_partial_exchange_cash_stock_history_and_isolation():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        ) as c:
            assert (
                await c.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200

            async def old(action, **kw):
                r = await c.post("/api/workspace", json={"action": action, **kw})
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Exchange test", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"
            products = []
            for sku, price in [("A", 1001), ("B", 2000)]:
                products.append(
                    (
                        await old(
                            "product",
                            tenant=tenant,
                            sku=sku,
                            name="Item " + sku,
                            category="General",
                            price=price,
                            cost=300,
                            initial=20,
                            reorder=1,
                        )
                    )["id"]
                )
            till = await c.post(base + "/tills", json={"opening_cash": 10000})
            assert till.status_code in (200, 201), till.text
            payload = dict(
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=[{"id": products[0], "quantity": 3}],
                payment="cash",
                expected=3192,
                tendered=4000,
                discount=101,
                tax_bps=1000,
            )
            sale = await old("checkout", **payload)
            url = base + f"/sales/{sale['id']}/adjustments"
            r = (await c.get(base + f"/sales/{sale['id']}")).json()
            item = r["items"][0]["id"]
            preview = dict(
                revision=0,
                returns=[dict(item=item, quantity=1, reason="damaged", restock=False)],
                replacements=[dict(id=products[1], quantity=1)],
                tax_bps=0,
            )
            q = await c.post(url + "/preview", json=preview)
            assert q.status_code == 200, q.text
            q = q.json()
            assert q["credit"] == 1064 and q["net"] == 936
            commit = {
                **preview,
                "request": uuid.uuid4().hex,
                "quote_token": q["quote_token"],
                "settlement": "cash",
                "tendered": 1000,
            }
            short = await c.post(url, json={**commit, "tendered": 935})
            assert short.status_code == 400, short.text
            posted = await c.post(url, json=commit)
            assert posted.status_code == 200, posted.text
            result = posted.json()
            assert result["change"] == 64 and result["revision"] == 1
            assert (await c.post(url, json=commit)).json() == result
            assert (
                await c.post(url, json={**commit, "tendered": 1100})
            ).status_code == 409
            # Original checkout retry must retain its original response after revisions.
            assert await old("checkout", **payload) == sale
            assert (await c.post(url + "/preview", json=preview)).status_code == 409
            receipt = (await c.get(base + f"/sales/{sale['id']}")).json()
            assert (
                receipt["sale"]["total"] == 2128
                and receipt["items"][0]["quantity"] == 2
            )
            assert "original_snapshot" not in receipt["sale"]
            assert len(receipt["sale"]["adjustments"]) == 1
            original = (await c.get(url + "/original")).json()
            assert (
                original["sale"]["total"] == 3192
                and Decimal(original["items"][0]["quantity"]) == 3
            )
            for language in ["en", "ur"]:
                pdf = await c.get(
                    f"/api/invoices/{sale['id']}.pdf",
                    params={"tenant": tenant, "language": language},
                )
                assert pdf.status_code == 200 and pdf.content.startswith(
                    b"%PDF"
                ), pdf.text
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT stock FROM products WHERE id=$1", products[0]
                    )
                    == 17
                )
                assert (
                    await conn.fetchval(
                        "SELECT stock FROM products WHERE id=$1", products[1]
                    )
                    == 19
                )
                assert (
                    await conn.fetchval(
                        "SELECT SUM(cash_amount) FROM sales WHERE tenant=$1", tenant
                    )
                    == 3192 + 936
                )
            original_pdf = await c.get(
                f"/api/invoices/{sale['id']}.pdf",
                params={"tenant": tenant, "original": "true", "language": "ur"},
            )
            assert original_pdf.status_code == 200 and original_pdf.content.startswith(
                b"%PDF"
            )
            # Pure refund of an unopened incorrect item: cash out, source-batch restock.
            second = dict(
                revision=1,
                returns=[dict(item=item, quantity=1, reason="incorrect", restock=True)],
            )
            q = (await c.post(url + "/preview", json=second)).json()
            posted = await c.post(
                url,
                json={
                    **second,
                    "request": uuid.uuid4().hex,
                    "quote_token": q["quote_token"],
                    "settlement": "cash",
                },
            )
            assert posted.status_code == 200, posted.text
            assert posted.json()["credit"] == 1064
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT stock FROM products WHERE id=$1", products[0]
                    )
                    == 18
                )
                assert (
                    await conn.fetchval(
                        "SELECT SUM(amount) FROM till_cash_movements WHERE tenant=$1",
                        tenant,
                    )
                    == -1064
                )
            # Cannot restore dangerous goods or return more than the remaining quantity.
            for changes in [
                dict(quantity=2),
                dict(reason="opened", restock=True),
                dict(reason="expired", restock=True),
            ]:
                invalid = dict(
                    revision=2, returns=[{**second["returns"][0], **changes}]
                )
                assert (await c.post(url + "/preview", json=invalid)).status_code == 400
            assert (
                await c.post(
                    base + f"/sales/{sale['id']}/returns",
                    json={"reason": "legacy bypass"},
                )
            ).status_code == 409
            # Final return external reference required; cumulative rounding credits exactly original total.
            last = dict(
                revision=2,
                returns=[dict(item=item, quantity=1, reason="expired", restock=False)],
            )
            q = (await c.post(url + "/preview", json=last)).json()
            final = {
                **last,
                "request": uuid.uuid4().hex,
                "quote_token": q["quote_token"],
                "settlement": "external",
            }
            assert (await c.post(url, json=final)).status_code == 400
            done = await c.post(
                url, json={**final, "reference": "Refund recorded at terminal R-3"}
            )
            assert done.status_code == 200, done.text
            assert done.json()["credit"] == 1064
            assert 1064 + 1064 + 1064 == 3192
            receipt = (await c.get(base + f"/sales/{sale['id']}")).json()
            assert (
                receipt["sale"]["status"] == "returned"
                and receipt["sale"]["total"] == 0
                and not receipt["items"]
            )
            # Inclusive tax and a failed replacement must preserve the entire transaction.
            async with db.pool.acquire() as conn:
                profile = uuid.uuid4().hex
                await conn.execute(
                    "INSERT INTO tax_profiles(id,tenant,name,rate_bps,inclusive) VALUES($1,$2,'VAT',1000,true)",
                    profile,
                    tenant,
                )
                await conn.execute(
                    "UPDATE tenants SET tax_mode='configured',default_tax_profile=$1 WHERE id=$2",
                    profile,
                    tenant,
                )
            cart = [dict(id=products[1], quantity=2)]
            tax_quote = (
                await c.post(base + "/sales/quote", json=dict(items=cart))
            ).json()
            fresh = await old(
                "checkout",
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=cart,
                payment="cash",
                tendered=4000,
                expected=4000,
                quote_token=tax_quote["quote_token"],
            )
            fresh_receipt = (await c.get(base + f"/sales/{fresh['id']}")).json()
            fresh_item = fresh_receipt["items"][0]["id"]
            fresh_url = base + f"/sales/{fresh['id']}/adjustments"
            bad = dict(
                revision=0,
                returns=[
                    dict(item=fresh_item, quantity=1, reason="opened", restock=False)
                ],
                replacements=[dict(id=products[0], quantity=100)],
            )
            quote = (await c.post(fresh_url + "/preview", json=bad)).json()
            denied = await c.post(
                fresh_url,
                json={
                    **bad,
                    "request": uuid.uuid4().hex,
                    "quote_token": quote["quote_token"],
                    "settlement": "external",
                    "reference": "QA",
                },
            )
            assert denied.status_code == 400, denied.text
            unchanged = (await c.get(base + f"/sales/{fresh['id']}")).json()
            assert (
                unchanged["sale"]["revision"] == 0
                and unchanged["items"][0]["quantity"] == 2
            )
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT stock FROM products WHERE id=$1", products[1]
                    )
                    == 17
                )
                await conn.execute(
                    "UPDATE stock_batches SET expires=current_date-1 WHERE tenant=$1 AND product=$2",
                    tenant,
                    products[1],
                )
            expired = dict(
                revision=0,
                returns=[
                    dict(item=fresh_item, quantity=1, reason="incorrect", restock=True)
                ],
            )
            quote = (await c.post(fresh_url + "/preview", json=expired)).json()
            assert (
                await c.post(
                    fresh_url,
                    json={
                        **expired,
                        "request": uuid.uuid4().hex,
                        "quote_token": quote["quote_token"],
                        "settlement": "cash",
                    },
                )
            ).status_code == 400
            expired["returns"][0].update(reason="expired", restock=False)
            quote = (await c.post(fresh_url + "/preview", json=expired)).json()
            assert quote["credit"] == 2000
            posted = await c.post(
                fresh_url,
                json={
                    **expired,
                    "request": uuid.uuid4().hex,
                    "quote_token": quote["quote_token"],
                    "settlement": "cash",
                },
            )
            assert posted.status_code == 200, posted.text
            remaining = (await c.get(base + f"/sales/{fresh['id']}")).json()
            assert (
                remaining["sale"]["tax"] == 182
                and remaining["sale"]["tax_included"] == 182
            )
            from app.features.operational_reports import tax_register

            assert tax_register([{**remaining["sale"], "day": "2026-10-25"}])
            # Return access and historical costs remain protected.
            email = uuid.uuid4().hex + "@example.com"
            await old(
                "member",
                tenant=tenant,
                email=email,
                name="Cashier",
                password="CashierPassword2026!",
                role="Cashier",
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as staff:
                await staff.post(
                    "/api/auth/login",
                    json=dict(email=email, password="CashierPassword2026!"),
                )
                assert (
                    await staff.post(fresh_url + "/preview", json=expired)
                ).status_code == 403
                assert (
                    await staff.post(
                        fresh_url,
                        json={
                            **expired,
                            "request": "denied",
                            "quote_token": quote["quote_token"],
                        },
                    )
                ).status_code == 403
                original_staff = (await staff.get(url + "/original")).json()
                assert "cost" not in original_staff["items"][0]
                assert "original_snapshot" not in original_staff["sale"]
            # Ambiguous partial batch restocking is rejected. Equal exchanges need no till.
            multi = (
                await old(
                    "product",
                    tenant=tenant,
                    sku="MULTI",
                    name="Multi batch",
                    category="General",
                    price=100,
                    cost=10,
                    initial=1,
                    reorder=1,
                )
            )["id"]
            await old(
                "movement",
                tenant=tenant,
                product=multi,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=1,
                lot="SECOND",
                notes="Second batch",
            )
            cart = [dict(id=multi, quantity=2)]
            tq = (await c.post(base + "/sales/quote", json=dict(items=cart))).json()
            ms = await old(
                "checkout",
                tenant=tenant,
                request=uuid.uuid4().hex,
                items=cart,
                payment="cash",
                expected=200,
                tendered=200,
                quote_token=tq["quote_token"],
            )
            mr = (await c.get(base + f"/sales/{ms['id']}")).json()
            mu = base + f"/sales/{ms['id']}/adjustments"
            mb = dict(
                revision=0,
                returns=[
                    dict(
                        item=mr["items"][0]["id"],
                        quantity=1,
                        reason="incorrect",
                        restock=True,
                    )
                ],
            )
            mq = (await c.post(mu + "/preview", json=mb)).json()
            rejected = await c.post(
                mu,
                json={
                    **mb,
                    "request": uuid.uuid4().hex,
                    "quote_token": mq["quote_token"],
                    "settlement": "external",
                    "reference": "R",
                },
            )
            assert (
                rejected.status_code == 400
                and "multiple original batches" in rejected.text
            )
            mb["returns"][0]["restock"] = False
            mq = (await c.post(mu + "/preview", json=mb)).json()
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE till_sessions SET status='closed' WHERE tenant=$1", tenant
                )
            assert (
                await c.post(
                    mu,
                    json={
                        **mb,
                        "request": uuid.uuid4().hex,
                        "quote_token": mq["quote_token"],
                        "settlement": "cash",
                    },
                )
            ).status_code == 409
            await old(
                "movement",
                tenant=tenant,
                product=multi,
                request=uuid.uuid4().hex,
                type="IN",
                quantity=1,
                lot="THIRD",
                notes="Replacement stock",
            )
            mb["replacements"] = [dict(id=multi, quantity=1)]
            mq = (await c.post(mu + "/preview", json=mb)).json()
            assert mq["net"] == 0
            equal = await c.post(
                mu,
                json={
                    **mb,
                    "request": uuid.uuid4().hex,
                    "quote_token": mq["quote_token"],
                    "settlement": "cash",
                },
            )
            assert equal.status_code == 200, equal.text
            # Cross-tenant invoice and product references fail without changing either business.
            other = (await old("tenant", name="Other exchange tenant", currency="PKR"))[
                "id"
            ]
            assert (
                await c.post(
                    f"/api/v1/tenants/{other}/sales/{sale['id']}/adjustments/preview",
                    json=preview,
                )
            ).status_code == 404
            # CSRF protection applies to both preview and commit.
            assert (
                await c.post(
                    url, json=commit, headers={"Origin": "http://wrong.example"}
                )
            ).status_code == 403
