"""Retail acceptance: exact money, approvals, repayments, and FEFO provenance."""

import os, uuid
from datetime import date, timedelta
from decimal import Decimal
import httpx, pytest
from app.features.credit import schedule
from app.rules import quantity, line_amount


@pytest.mark.parametrize("total,count", [(100, 3), (10001, 7), (60, 60)])
def test_installment_totals_are_exact(total, count):
    rows = schedule(total, count, date(2027, 1, 31), "monthly")
    assert sum(x["amount"] for x in rows) == total
    assert all(x["amount"] > 0 for x in rows)
    if count > 2:
        assert rows[1]["due_date"] == date(2027, 2, 28)
        assert rows[2]["due_date"] == date(2027, 3, 31)


def test_weighted_money_uses_half_up():
    assert line_amount(101, quantity("1.5")) == 152
    assert quantity("0.001") == Decimal("0.001")
    with pytest.raises(Exception):
        quantity("0.0001")
    with pytest.raises(Exception):
        quantity(True)


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_khata_installments_weighted_goods_and_expiry():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": config.APP_ORIGIN},
        ) as owner:
            assert (
                await owner.post(
                    "/api/auth/login",
                    json={
                        "email": config.ADMIN_EMAIL,
                        "password": config.ADMIN_PASSWORD,
                    },
                )
            ).status_code == 200

            async def old(action, **payload):
                r = await owner.post(
                    "/api/workspace", json={"action": action, **payload}
                )
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await old("tenant", name="Retail tests", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"
            other = (await old("tenant", name="Other tests", currency="PKR"))["id"]

            async def look(kind, code):
                return next(
                    x
                    for x in (
                        await owner.get(base + "/lookups", params={"kind": kind})
                    ).json()["items"]
                    if x["code"] == code
                )["id"]

            category = await look("category", "general")
            kg = await look("unit", "kg")
            piece = await look("unit", "piece")
            cash = await look("payment_method", "cash")
            code = uuid.uuid4().hex[:8]
            email = f"cashier-{code}@example.com"
            password = "CashierPassword!2026"
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
                base_url="http://testserver",
                headers={"Origin": config.APP_ORIGIN},
            ) as cashier:
                assert (
                    await cashier.post(
                        "/api/auth/login", json={"email": email, "password": password}
                    )
                ).status_code == 200
                c = await cashier.post(
                    base + "/customers",
                    json={
                        "name": "Ali Khan",
                        "phone": "03000000000",
                        "search_aliases": "ali khan karachi",
                    },
                )
                assert c.status_code == 201, c.text
                customer = c.json()["id"]
                assert (
                    len(
                        (await cashier.get(base + "/customers?q=karachi")).json()[
                            "items"
                        ]
                    )
                    == 1
                )
                req = (
                    await cashier.post(
                        base + "/credit-requests",
                        json={
                            "customer": customer,
                            "proposed_limit": 200000,
                            "reason": "Regular customer",
                        },
                    )
                ).json()["id"]
                assert (
                    await cashier.post(
                        base + f"/credit-requests/{req}/decision",
                        json={"decision": "approved", "note": "Not allowed"},
                    )
                ).status_code == 403
                assert (
                    await owner.post(
                        base + f"/credit-requests/{req}/decision",
                        json={"decision": "approved", "note": "Verified by owner"},
                    )
                ).status_code == 200
                own_req = (
                    await owner.post(
                        base + "/credit-requests",
                        json={
                            "customer": customer,
                            "proposed_limit": 300000,
                            "reason": "Increase",
                        },
                    )
                ).json()["id"]
                assert (
                    await owner.post(
                        base + f"/credit-requests/{own_req}/decision",
                        json={"decision": "approved", "note": "Self approval"},
                    )
                ).status_code == 403
                p = await owner.post(
                    base + "/products",
                    json={
                        "sku": "RICE-KG",
                        "name": "Loose rice",
                        "category_id": category,
                        "unit_id": kg,
                        "price": 10000,
                        "cost": 6000,
                        "initial": 10.5,
                    },
                )
                assert p.status_code == 201, p.text
                product = p.json()["id"]
                bad = await owner.post(
                    base + "/products",
                    json={
                        "sku": "PIECE",
                        "name": "Piece",
                        "category_id": category,
                        "unit_id": piece,
                        "price": 10000,
                        "initial": 0.5,
                    },
                )
                assert bad.status_code == 400
                cross = await owner.post(
                    f"/api/v1/tenants/{other}/products",
                    json={
                        "sku": "CROSS",
                        "name": "Bad",
                        "category_id": category,
                        "unit_id": kg,
                        "price": 1,
                    },
                )
                assert cross.status_code == 400
                products = (await cashier.get(base + "/products")).json()["items"]
                assert "cost" not in products[0]
                snapshot = (
                    await cashier.get("/api/workspace", params={"tenant": tenant})
                ).json()
                assert "cost" not in snapshot["products"][0]
                opened = await cashier.post(
                    base + "/tills", json={"opening_cash": 10000}
                )
                assert opened.status_code == 200, opened.text
                till = opened.json()["id"]
                assert (
                    await cashier.post(base + "/tills", json={"opening_cash": 0})
                ).status_code == 409
                due = (date.today() + timedelta(days=30)).isoformat()
                payload = {
                    "request": uuid.uuid4().hex,
                    "items": [{"id": product, "quantity": 1.25}],
                    "customer_id": customer,
                    "paid_now": 2500,
                    "due_date": due,
                    "payment_method_id": cash,
                    "payment": "cash",
                    "expected": 12500,
                    "tendered": 2500,
                }
                response = await cashier.post(base + "/sales", json=payload)
                assert response.status_code == 200, response.text
                sale = response.json()["id"]
                assert response.json()["credit_amount"] == 10000
                assert (await cashier.post(base + "/sales", json=payload)).json()[
                    "id"
                ] == sale
                receipt = (await cashier.get(base + f"/sales/{sale}")).json()
                assert "cost" not in receipt["items"][0]
                assert receipt["items"][0]["line_total"] == 12500
                statement = (
                    await cashier.get(base + f"/customers/{customer}/statement")
                ).json()
                assert statement["balance"] == 10000
                rid = statement["documents"][0]["id"]
                plan = await owner.post(
                    base + "/installment-plans",
                    json={
                        "receivable": rid,
                        "frequency": "monthly",
                        "installments": 3,
                        "first_due": due,
                        "markup": 1000,
                    },
                )
                assert plan.status_code == 200, plan.text
                recovery = {
                    "request": uuid.uuid4().hex,
                    "customer": customer,
                    "amount": 4000,
                    "method": cash,
                    "reference": "Cash received",
                }
                response = await cashier.post(base + "/recoveries", json=recovery)
                assert response.status_code == 200, response.text
                assert (await cashier.post(base + "/recoveries", json=recovery)).json()[
                    "id"
                ] == response.json()["id"]
                assert (
                    await cashier.post(
                        base + "/recoveries", json={**recovery, "amount": 4001}
                    )
                ).status_code == 409
                over = await cashier.post(
                    base + "/recoveries",
                    json={**recovery, "request": uuid.uuid4().hex, "amount": 8000},
                )
                assert over.status_code == 409
                statement = (
                    await cashier.get(base + f"/customers/{customer}/statement")
                ).json()
                assert statement["balance"] == 7000
                assert sum(s["paid"] for s in statement["schedule"]) == 4000
                assert (
                    await cashier.get(base + f"/customers/{customer}/statement.pdf")
                ).content.startswith(b"%PDF")
                assert (
                    await cashier.get(
                        f"/api/v1/tenants/{other}/customers/{customer}/statement"
                    )
                ).status_code == 403
                returned = await owner.post(
                    base + f"/sales/{sale}/returns", json={"reason": "Return all"}
                )
                assert returned.status_code == 200, returned.text
                assert returned.json()["external_refund_due"] == 6500
                assert (
                    await owner.post(
                        base + f"/sales/{sale}/returns", json={"reason": "Retry"}
                    )
                ).status_code == 200
                statement = (
                    await cashier.get(base + f"/customers/{customer}/statement")
                ).json()
                assert statement["balance"] == 0
                assert not (await cashier.get(base + "/credit-overview")).json()["dues"]
                assert (await owner.get(base + "/products")).json()["items"][0][
                    "stock"
                ] == 10.5
                totals = (await cashier.get(base + "/tills")).json()["totals"]
                assert totals["expected"] == 16500, totals
                cashout = {
                    "request": uuid.uuid4().hex,
                    "type": "OUT",
                    "amount": 6500,
                    "reason": "Refund actually paid",
                }
                r = await cashier.post(
                    base + f"/tills/{till}/cash-movements", json=cashout
                )
                assert r.status_code == 200, r.text
                assert (
                    await cashier.post(
                        base + f"/tills/{till}/cash-movements", json=cashout
                    )
                ).json()["id"] == r.json()["id"]
                assert (
                    await cashier.post(
                        base + f"/tills/{till}/close", json={"counted_cash": 9999}
                    )
                ).status_code == 400
                closed = await cashier.post(
                    base + f"/tills/{till}/close", json={"counted_cash": 10000}
                )
                assert closed.status_code == 200, closed.text
                assert closed.json()["variance"] == 0
                hold = {
                    "id": uuid.uuid4().hex,
                    "label": "Waiting customer",
                    "items": [{"id": product, "quantity": 0.5}],
                }
                assert (
                    await cashier.post(base + "/held-bills", json=hold)
                ).status_code == 200
                assert (
                    len((await cashier.get(base + "/held-bills")).json()["items"]) == 1
                )
                assert not (await owner.get(base + "/held-bills")).json()["items"]
                heldsale = {
                    "request": uuid.uuid4().hex,
                    "items": hold["items"],
                    "held_bill_id": hold["id"],
                    "payment": "cash",
                    "expected": 5000,
                    "tendered": 5000,
                }
                r = await cashier.post(base + "/sales", json=heldsale)
                assert r.status_code == 200, r.text
                assert (await cashier.post(base + "/sales", json=heldsale)).json()[
                    "id"
                ] == r.json()["id"]
                assert (
                    await cashier.post(
                        base + "/sales", json={**heldsale, "request": uuid.uuid4().hex}
                    )
                ).status_code == 409
                assert not (await cashier.get(base + "/held-bills")).json()["items"]
                # Lot provenance and expiry rules.
                med = await owner.post(
                    base + "/products",
                    json={
                        "sku": "MED",
                        "name": "Medicine example",
                        "category_id": category,
                        "unit_id": piece,
                        "price": 1000,
                        "expiry_required": True,
                        "prescription_required": True,
                    },
                )
                assert med.status_code == 201, med.text
                mid = med.json()["id"]
                for lot, expiry, qty in [
                    ("EXPIRED", date.today() - timedelta(days=2), 5),
                    ("LATER", date.today() + timedelta(days=90), 4),
                    ("FIRST", date.today() + timedelta(days=10), 3),
                ]:
                    r = await owner.post(
                        base + "/stock-adjustments",
                        json={
                            "request": uuid.uuid4().hex,
                            "product": mid,
                            "type": "IN",
                            "quantity": qty,
                            "notes": "Delivery",
                            "lot": lot,
                            "expires": expiry.isoformat(),
                        },
                    )
                    assert r.status_code == 200, r.text
                buy = {
                    "request": uuid.uuid4().hex,
                    "items": [{"id": mid, "quantity": 2}],
                    "payment": "cash",
                    "expected": 2000,
                    "tendered": 2000,
                }
                assert (
                    await cashier.post(base + "/sales", json=buy)
                ).status_code == 400
                buy["prescription_reference"] = "RX-TEST"
                r = await cashier.post(base + "/sales", json=buy)
                assert r.status_code == 200, r.text
                med_sale = r.json()["id"]
                batches = (
                    await owner.get(base + "/batches", params={"product": mid})
                ).json()["items"]
                assert next(b for b in batches if b["lot"] == "FIRST")["stock"] == 1
                assert next(b for b in batches if b["lot"] == "EXPIRED")["stock"] == 5
                assert (
                    await owner.post(
                        base + f"/sales/{med_sale}/returns",
                        json={"reason": "Return sealed goods"},
                    )
                ).status_code == 200
                batches = (
                    await owner.get(base + "/batches", params={"product": mid})
                ).json()["items"]
                assert next(b for b in batches if b["lot"] == "FIRST")["stock"] == 3
                overbuy = {
                    **buy,
                    "request": uuid.uuid4().hex,
                    "items": [{"id": mid, "quantity": 8}],
                    "expected": 8000,
                    "tendered": 8000,
                }
                assert (
                    await cashier.post(base + "/sales", json=overbuy)
                ).status_code == 400
                alerts = (await owner.get(base + "/inventory-alerts")).json()
                assert len(alerts["expired"]) == 1
                assert len(alerts["near_expiry"]) == 1
                # Updating a lookup label preserves IDs; deactivation blocks new catalog assignments.
                unit = (await owner.get(base + f"/lookups/{kg}")).json()
                changed = {
                    k: unit[k]
                    for k in ("kind", "code", "name", "name_ur", "active", "sort_order")
                }
                changed["active"] = False
                assert (
                    await owner.put(base + f"/lookups/{kg}", json=changed)
                ).status_code == 200
                assert (
                    await owner.post(
                        base + "/products",
                        json={
                            "sku": "NEW",
                            "name": "Blocked",
                            "category_id": category,
                            "unit_id": kg,
                            "price": 100,
                        },
                    )
                ).status_code == 400
                async with db.pool.acquire() as c:
                    with pytest.raises(Exception):
                        await c.execute(
                            "UPDATE customer_ledger SET reference='tamper' WHERE tenant=$1",
                            tenant,
                        )
                    sums = await c.fetch(
                        "SELECT p.id,p.stock,COALESCE(SUM(b.stock),0) AS batches FROM products p LEFT JOIN stock_batches b ON b.tenant=p.tenant AND b.product=p.id WHERE p.tenant=$1 GROUP BY p.id",
                        tenant,
                    )
                    assert all(x["stock"] == x["batches"] for x in sums)
