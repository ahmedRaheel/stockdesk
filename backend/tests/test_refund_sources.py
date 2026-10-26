"""Original-method refunds preserve provenance through split payments and exchanges."""

import os, uuid
import httpx, pytest


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_refund_capacity_exchange_provenance_recoveries():
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
            await c.post(
                "/api/auth/login",
                json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )

            async def old(action, **kw):
                r = await c.post("/api/workspace", json=dict(action=action, **kw))
                assert r.status_code == 200, r.text
                return r.json()

            t = (await old("tenant", name="Original refund QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}"

            async def post(path, body):
                r = await c.post(base + path, json=body)
                assert r.status_code in (200, 201), r.text
                return r.json()

            a = (
                await old(
                    "product",
                    tenant=t,
                    sku="A",
                    name="A",
                    category="General",
                    price=1000,
                    cost=100,
                    initial=30,
                    reorder=0,
                )
            )["id"]
            b = (
                await old(
                    "product",
                    tenant=t,
                    sku="B",
                    name="B",
                    category="General",
                    price=500,
                    cost=100,
                    initial=30,
                    reorder=0,
                )
            )["id"]
            async with db.pool.acquire() as conn:
                cash = await conn.fetchval(
                    "SELECT id FROM lookups WHERE tenant=$1 AND kind='payment_method' AND code='cash'",
                    t,
                )
                bank = await conn.fetchval(
                    "SELECT id FROM lookups WHERE tenant=$1 AND kind='payment_method' AND code='bank'",
                    t,
                )
            await post("/tills", dict(opening_cash=10000))
            sale = await post(
                "/sales",
                dict(
                    request=uuid.uuid4().hex,
                    items=[dict(id=a, quantity=4)],
                    payment="cash",
                    expected=4000,
                    paid_now=4000,
                    tendered=1000,
                    tenders=[
                        dict(method_id=cash, amount=1000),
                        dict(
                            method_id=bank,
                            amount=3000,
                            reference="Original bank receipt",
                        ),
                    ],
                ),
            )

            async def body(sid, revision, qty, replacements=None):
                receipt = (await c.get(base + f"/sales/{sid}")).json()
                return dict(
                    original_methods=True,
                    revision=revision,
                    returns=[
                        dict(
                            item=receipt["items"][0]["id"],
                            quantity=qty,
                            reason="damaged",
                        )
                    ],
                    replacements=replacements or [],
                )

            async def quote(sid, payload):
                return await post(f"/sales/{sid}/adjustments/preview", payload)

            def refs(q):
                return [
                    dict(source=p["source"], reference="Bank refund confirmed")
                    for p in q["payment_allocation"]["refunds"]
                    if not p["is_cash"]
                ]

            async def commit(sid, payload, q):
                req = dict(
                    **payload,
                    request=uuid.uuid4().hex,
                    quote_token=q["quote_token"],
                    settlement="original",
                    refund_references=refs(q),
                )
                result = await post(f"/sales/{sid}/adjustments", req)
                assert await post(f"/sales/{sid}/adjustments", req) == result
                return result

            payload = await body(sale["id"], 0, 1)
            q = await quote(sale["id"], payload)
            assert q["payment_allocation"]["cash_refund"] == 250
            req = dict(
                **payload,
                request=uuid.uuid4().hex,
                quote_token=q["quote_token"],
                settlement="original",
            )
            for invalid in (
                [],
                [dict(source="foreign", reference="Unknown")],
                refs(q) * 2,
            ):
                r = await c.post(
                    base + f"/sales/{sale['id']}/adjustments",
                    json={**req, "refund_references": invalid},
                )
                assert r.status_code == 400, r.text
            assert (await c.get(base + f"/sales/{sale['id']}")).json()["sale"][
                "revision"
            ] == 0
            first = await commit(sale["id"], payload, q)
            assert first["cash_refund"] == 250 and len(first["refunds"]) == 2
            payload = await body(sale["id"], 1, 1, [dict(id=b, quantity=1)])
            q = await quote(sale["id"], payload)
            assert q["net"] == -500 and q["payment_allocation"]["cash_refund"] == 125
            second = await commit(sale["id"], payload, q)
            replacement = second["replacement_sale"]
            rec = (await c.get(base + f"/sales/{replacement}")).json()
            assert (
                rec["sale"]["cash_amount"] == 0
                and sum(p["amount"] for p in rec["tenders"]) == 500
                and all(p["carried_credit"] for p in rec["tenders"])
            )
            payload = await body(sale["id"], 2, 2)
            q = await quote(sale["id"], payload)
            third = await commit(sale["id"], payload, q)
            assert third["cash_refund"] == 500
            payload = await body(replacement, 0, 1)
            q = await quote(replacement, payload)
            fourth = await commit(replacement, payload, q)
            assert fourth["cash_refund"] == 125
            payouts = (
                first["refunds"]
                + second["refunds"]
                + third["refunds"]
                + fourth["refunds"]
            )
            assert sum(p["amount"] for p in payouts if p["is_cash"]) == 1000
            assert sum(p["amount"] for p in payouts if not p["is_cash"]) == 3000
            assert (await c.get(base + "/tills")).json()["totals"]["expected"] == 10000
            for lang in ("en", "ur"):
                r = await c.get(
                    f"/api/invoices/{sale['id']}.pdf",
                    params={"tenant": t, "language": lang},
                )
                assert r.status_code == 200 and r.content.startswith(b"%PDF")
            # Recoveries carry frozen method information and are refundable only after debt credit.
            customer = await post(
                "/customers", dict(name="Khata refund", phone="03000000000")
            )
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE customers SET credit_enabled=true,credit_limit=10000 WHERE id=$1",
                    customer["id"],
                )
            ks = await post(
                "/sales",
                dict(
                    request=uuid.uuid4().hex,
                    items=[dict(id=a, quantity=2)],
                    payment="cash",
                    expected=2000,
                    paid_now=0,
                    tendered=0,
                    customer_id=customer["id"],
                    due_date="2099-01-01",
                ),
            )
            await post(
                "/recoveries",
                dict(
                    request=uuid.uuid4().hex,
                    customer=customer["id"],
                    amount=800,
                    method=bank,
                    reference="Recovery bank receipt",
                ),
            )
            payload = await body(ks["id"], 0, 2)
            q = await quote(ks["id"], payload)
            assert q["debt_credit"] == 1200 and q["net"] == -800
            # A later recovery changes the payment allocation and invalidates the quote.
            await post(
                "/recoveries",
                dict(
                    request=uuid.uuid4().hex,
                    customer=customer["id"],
                    amount=200,
                    method=cash,
                    reference="Recovery cash",
                ),
            )
            denied = await c.post(
                base + f"/sales/{ks['id']}/adjustments",
                json=dict(
                    **payload,
                    request=uuid.uuid4().hex,
                    quote_token=q["quote_token"],
                    settlement="original",
                    refund_references=refs(q),
                ),
            )
            assert denied.status_code == 409
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE lookups SET name='Renamed bank' WHERE id=$1", bank
                )
            q = await quote(ks["id"], payload)
            result = await commit(ks["id"], payload, q)
            assert result["cash_refund"] == 200 and len(result["refunds"]) == 2
            assert (
                next(p["name"] for p in result["refunds"] if not p["is_cash"])
                == "Bank transfer"
            )
            # Old adjustments without source evidence remain explicitly manual, never guessed.
            oldsale = await post(
                "/sales",
                dict(
                    request=uuid.uuid4().hex,
                    items=[dict(id=a, quantity=2)],
                    payment="cash",
                    expected=2000,
                    tendered=2000,
                ),
            )
            payload = await body(oldsale["id"], 0, 1)
            q = await quote(oldsale["id"], payload)
            oldresult = await commit(oldsale["id"], payload, q)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE sale_adjustments SET result=result-'source_usage' WHERE id=$1",
                    oldresult["id"],
                )
            payload = await body(oldsale["id"], 1, 1)
            denied = await c.post(
                base + f"/sales/{oldsale['id']}/adjustments/preview", json=payload
            )
            assert denied.status_code == 409
            payload["original_methods"] = False
            q = await quote(oldsale["id"], payload)
            assert not q["payment_allocation"]["available"]
            # Original-mode cannot be used to collect additional funds.
            new = await post(
                "/sales",
                dict(
                    request=uuid.uuid4().hex,
                    items=[dict(id=b, quantity=1)],
                    payment="cash",
                    expected=500,
                    tendered=500,
                ),
            )
            payload = await body(new["id"], 0, 1, [dict(id=a, quantity=1)])
            assert (
                await c.post(
                    base + f"/sales/{new['id']}/adjustments/preview", json=payload
                )
            ).status_code == 400
