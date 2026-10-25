import os, uuid
import pytest, httpx
from app.features.taxation import calculate, allocate_discount


def test_discount_allocation_preserves_every_minor_unit():
    assert allocate_discount([101, 101, 101], 2) == [1, 1, 0]
    assert sum(allocate_discount([199, 289, 599], 107)) == 107


def test_mixed_tax_and_disabled_mode():
    lines = [
        {"id": "a", "line_total": 11800, "rate_bps": 1800, "inclusive": True},
        {"id": "b", "line_total": 10000, "rate_bps": 1800, "inclusive": False},
        {"id": "c", "line_total": 1000, "rate_bps": 0},
    ]
    q = calculate(lines, 0, "configured")
    assert q["tax"] == 3600 and q["tax_included"] == 1800 and q["total"] == 24600
    assert calculate(lines, 0, "disabled")["total"] == 22800
    discounted = calculate(lines, 2280, "configured")
    assert discounted["tax"] == 3240 and discounted["total"] == 22140


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_configured_tax_quote_checkout_and_tenant_isolation():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Origin": config.APP_ORIGIN},
        ) as c:
            r = await c.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )
            assert r.status_code == 200, r.text
            tid = (
                await c.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": "Tax tests", "currency": "PKR"},
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"
            unit = (await c.get(base + "/lookups", params={"kind": "unit"})).json()[
                "items"
            ][0]["id"]
            profile = {
                "name": "GST test",
                "name_ur": "ٹیکس",
                "rate_bps": 1800,
                "inclusive": True,
                "active": True,
            }
            r = await c.post(base + "/tax-profiles", json=profile)
            assert r.status_code == 201, r.text
            taxid = r.json()["id"]
            assert (
                await c.put(
                    base + "/tax-settings",
                    json={"mode": "configured", "default_profile": taxid},
                )
            ).status_code == 200
            p = await c.post(
                base + "/products",
                json={
                    "sku": "TAX",
                    "name": "Tax product",
                    "category": "General",
                    "unit_id": unit,
                    "price": 11800,
                    "initial": 10,
                },
            )
            assert p.status_code == 201, p.text
            pid = p.json()["id"]
            payload = {
                "items": [{"id": pid, "quantity": 1}],
                "discount": 0,
                "tax_bps": 9999,
            }
            r = await c.post(base + "/sales/quote", json=payload)
            assert r.status_code == 200, r.text
            q = r.json()
            assert (
                q["total"] == 11800 and q["tax"] == 1800 and q["tax_included"] == 1800
            )
            sale = {
                **payload,
                "request": uuid.uuid4().hex,
                "payment": "cash",
                "expected": 11800,
                "tendered": 11800,
                "quote_token": q["quote_token"],
            }
            r = await c.post(base + "/sales", json=sale)
            assert r.status_code == 200, r.text
            sid = r.json()["id"]
            assert (await c.post(base + "/sales", json=sale)).json()["id"] == sid
            receipt = (await c.get(base + "/sales/" + sid)).json()
            assert receipt["sale"]["tax_included"] == 1800
            profile["rate_bps"] = 1700
            assert (
                await c.put(base + "/tax-profiles/" + taxid, json=profile)
            ).status_code == 200
            stale = await c.post(
                base + "/sales", json={**sale, "request": uuid.uuid4().hex}
            )
            assert stale.status_code == 409, stale.text
            assert (await c.get(base + "/sales/" + sid)).json()["sale"]["tax"] == 1800
            assert (
                await c.get(f"/api/invoices/{sid}.pdf?tenant={tid}")
            ).content.startswith(b"%PDF")
            profile["ends_on"] = "2000-01-01"
            assert (
                await c.put(base + "/tax-profiles/" + taxid, json=profile)
            ).status_code == 200
            assert (
                await c.post(base + "/sales/quote", json=payload)
            ).status_code == 409
            assert (
                await c.put(base + "/tax-settings", json={"mode": "disabled"})
            ).status_code == 200
            q = (await c.post(base + "/sales/quote", json=payload)).json()
            assert q["tax"] == 0 and q["total"] == 11800
            methods = (
                await c.get(base + "/lookups", params={"kind": "payment_method"})
            ).json()["items"]
            cash = next(x["id"] for x in methods if x["code"] == "cash")
            bank = next(x["id"] for x in methods if x["code"] == "bank")
            opened = await c.post(base + "/tills", json={"opening_cash": 1000})
            assert opened.status_code == 200, opened.text
            split = {
                **sale,
                "request": uuid.uuid4().hex,
                "quote_token": q["quote_token"],
                "paid_now": 11800,
                "tendered": 5000,
                "tenders": [
                    {"method_id": cash, "amount": 5000},
                    {
                        "method_id": bank,
                        "amount": 6800,
                        "reference": "verified external receipt",
                    },
                ],
            }
            r = await c.post(base + "/sales", json=split)
            assert r.status_code == 200, r.text
            split_id = r.json()["id"]
            assert (await c.post(base + "/sales", json=split)).json()["id"] == split_id
            parts = (await c.get(base + "/sales/" + split_id)).json()["tenders"]
            assert sum(p["amount"] for p in parts) == 11800
            assert (await c.get(base + "/tills")).json()["totals"]["expected"] == 6000
            bad = {
                **split,
                "request": uuid.uuid4().hex,
                "tenders": [{"method_id": cash, "amount": 10}],
            }
            assert (await c.post(base + "/sales", json=bad)).status_code == 400
            ur = await c.get(f"/api/invoices/{split_id}.pdf?tenant={tid}&language=ur")
            assert ur.content.startswith(b"%PDF"), ur.text
            # New business units can allow fractions; rules become immutable once used.
            unitres = await c.post(
                base + "/lookups",
                json={
                    "kind": "unit",
                    "code": "custom-weight",
                    "name": "Weight",
                    "fractional": True,
                },
            )
            assert unitres.status_code == 201, unitres.text
            uid = unitres.json()["id"]
            assert (await c.get(base + "/lookups/" + uid)).json()["fractional"] is True
            assert (
                await c.post(
                    base + "/products",
                    json={
                        "sku": "WEIGHT",
                        "name": "Weighted",
                        "category": "General",
                        "unit_id": uid,
                        "price": 100,
                        "initial": 0.125,
                    },
                )
            ).status_code == 201
            assert (
                await c.put(
                    base + "/lookups/" + uid,
                    json={
                        "kind": "unit",
                        "code": "custom-weight",
                        "name": "Weight",
                        "fractional": False,
                    },
                )
            ).status_code == 400
            other = (
                await c.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": "Other tax", "currency": "PKR"},
                )
            ).json()["id"]
            assert (
                await c.put(
                    f"/api/v1/tenants/{other}/tax-settings",
                    json={"mode": "configured", "default_profile": taxid},
                )
            ).status_code == 400
