from datetime import date, datetime, timezone
from decimal import Decimal
import os
import uuid
import pytest
import httpx
from fastapi import HTTPException
from app.features.operational_reports import (
    tax_register,
    stock_age,
    basket_analysis,
    scenario,
)


def test_tax_register_frozen_mixed_tax_and_manual_legacy():
    sales = [
        dict(
            id="s",
            invoice_number="INV-1",
            day=date(2026, 1, 1),
            subtotal=21800,
            discount=2180,
            tax=3240,
            tax_included=1620,
            tax_bps=0,
            total=21240,
            tax_snapshot={
                "lines": [
                    dict(
                        profile_id="inc",
                        name="VAT",
                        rate_bps=1800,
                        inclusive=True,
                        tax=1620,
                        taxable=9000,
                    ),
                    dict(
                        profile_id="exc",
                        name="VAT",
                        rate_bps=1800,
                        inclusive=False,
                        tax=1620,
                        taxable=9000,
                    ),
                ]
            },
        ),
        dict(
            id="legacy",
            invoice_number="INV-2",
            day=date(2026, 1, 1),
            subtotal=1000,
            discount=0,
            tax=50,
            tax_included=0,
            tax_bps=500,
            total=1050,
        ),
    ]
    r = tax_register(sales)
    assert r["summary"] == dict(
        taxable=19000, tax=3290, tax_included=1620, tax_added=1670, total=22290
    )
    assert len(r["groups"]) == 3
    assert r["groups"][0]["inclusive"] is True
    sales[0]["tax"] += 1
    with pytest.raises(HTTPException):
        tax_register(sales)


def test_stock_age_boundaries_and_exact_fractional_values():
    rows = []
    for i, expires in enumerate(
        [date(2026, 1, 30), date(2026, 1, 31), date(2026, 3, 2), None]
    ):
        rows.append(
            dict(
                id=str(i),
                sku=str(i),
                name="Product",
                lot="B",
                unit_name="kg",
                cost=101,
                stock=Decimal("0.5"),
                created=datetime(2026, 1, 1, tzinfo=timezone.utc),
                expires=expires,
            )
        )
    r = stock_age(rows, date(2026, 1, 31))
    assert r["summary"] == dict(
        current_cost_value=204, expired_value=51, near_expiry_value=102
    )
    assert [b["status"] for b in r["batches"]] == [
        "Expired",
        "Near expiry",
        "Near expiry",
        "Available",
    ]
    assert r["batches"][0]["age_days"] == 30
    assert r["batches"][0]["age_band"] == "0–30"


def test_baskets_deduplicate_units_denominators_and_minimum():
    sales = [dict(id=x) for x in "1234"]
    items = [
        dict(sale=s, product=p)
        for s, ps in [
            ("1", "aab"),
            ("2", "ab"),
            ("3", "a"),
            ("4", "c"),
            ("returned", "ab"),
        ]
        for p in ps
    ]
    products = [dict(id=x, sku=x, name=x.upper()) for x in "abc"]
    r = basket_analysis(sales, items, products)
    assert r["pairs"] == [
        dict(
            product_a="A",
            sku_a="a",
            product_b="B",
            sku_b="b",
            baskets=2,
            support_pct=50.0,
            confidence_a_b_pct=66.67,
            confidence_b_a_pct=100.0,
            lift=1.3333,
        )
    ]
    assert not basket_analysis(sales, items, products, 3)["pairs"]
    assert not basket_analysis([], [], [])["pairs"]


def test_scenario_independent_changes_zero_sales_and_rounding():
    r = scenario(dict(net_sales=30000, cost=18000), 30, 10, 20, -10, 10)
    assert r["net_sales"] == 10800 and r["cost"] == 7920
    assert r["profit"] == 2880 and r["profit_change"] == -1120
    assert scenario(dict(net_sales=1, cost=0), 2, 1, 0, 0, 0)["net_sales"] == 1
    assert scenario(dict(net_sales=0, cost=0), 30, 30, 0, 0, 0)["margin_pct"] is None
    assert scenario(dict(net_sales=300, cost=200), 30, 30, -100, 0, 0)["profit"] == 0


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_operational_api_tenant_permissions_and_sale_return():
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

            async def post(action, tenant="", **kw):
                r = await c.post(
                    "/api/workspace", json=dict(action=action, tenant=tenant, **kw)
                )
                assert r.status_code == 200, r.text
                return r.json()

            tenant = (await post("tenant", name="Analytics test", currency="PKR"))["id"]
            other = (await post("tenant", name="Empty analytics", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{tenant}"
            product = (
                await post(
                    "product",
                    tenant,
                    sku="A",
                    name="Example",
                    category="General",
                    price=1000,
                    cost=600,
                    initial=10,
                    reorder=0,
                )
            )["id"]
            sale = await post(
                "checkout",
                tenant,
                request=uuid.uuid4().hex,
                items=[dict(id=product, quantity=2)],
                customer="Walk-in customer",
                payment="cash",
                discount=0,
                tax_bps=1000,
                expected=2200,
                tendered=2200,
            )
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE sales SET created=now()-interval '1 day' WHERE tenant=$1 AND id=$2",
                    tenant,
                    sale["id"],
                )
            response = await c.get(base + "/operational-report")
            assert response.status_code == 200, response.text
            r = response.json()
            assert r["tax"]["summary"]["tax"] == 200
            assert r["scenario"]["profit"] == 800
            assert r["stock"]["summary"]["current_cost_value"] == 4800
            assert (await c.get(f"/api/v1/tenants/{other}/operational-report")).json()[
                "tax"
            ]["invoices"] == []
            assert (
                await c.get(base + "/operational-report?demand_pct=-101")
            ).status_code == 422
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE products SET created=now()-interval '31 days' WHERE tenant=$1",
                    tenant,
                )
                await conn.execute(
                    "UPDATE movements SET created=now()-CASE WHEN type='SALE' THEN interval '1 day' ELSE interval '30 days' END WHERE tenant=$1",
                    tenant,
                )
            turnover = (await c.get(base + "/inventory-turnover?days=7")).json()
            line = turnover["items"][0]
            assert line["opening"] == 10 and line["closing"] == 8 and line["sold"] == 2
            assert (
                str(line["turnover"]) == "0.2059" and float(line["days_per_turn"]) == 34
            )
            assert (await c.get(f"/api/v1/tenants/{other}/inventory-turnover")).json()[
                "items"
            ] == []
            assert (await c.get(base + "/inventory-turnover?days=0")).status_code == 422
            for name in [
                "products",
                "categories",
                "cashiers",
                "hours",
                "tax-summary",
                "tax-invoices",
                "stock-age",
                "basket-analysis",
                "what-if",
                "turnover",
            ]:
                for format in ["xlsx", "pdf"]:
                    exported = await c.get(
                        base + f"/report-export/{name}.{format}?days=7&demand_pct=20"
                    )
                    assert exported.status_code == 200, exported.text
                    assert exported.content.startswith(
                        b"PK" if format == "xlsx" else b"%PDF"
                    )
                    assert exported.headers["cache-control"] == "no-store"
            assert (
                await c.get(base + "/report-export/unknown.xlsx")
            ).status_code == 422
            assert (
                await c.get(base + "/report-export/products.exe")
            ).status_code == 422
            await post("return", tenant, id=sale["id"], reason="Return test")
            # A return posted today must not rewrite yesterday's stock turnover.
            after = (await c.get(base + "/inventory-turnover?days=7")).json()["items"][
                0
            ]
            assert (
                after["closing"] == 8 and after["returned"] == 0 and after["sold"] == 2
            )
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE movements SET created=now()-interval '1 day' WHERE tenant=$1 AND type='RETURN'",
                    tenant,
                )
            after = (await c.get(base + "/inventory-turnover?days=7")).json()["items"][
                0
            ]
            assert (
                after["closing"] == 10
                and after["returned"] == 2
                and float(after["net_units"]) == 0
            )

            r = (await c.get(base + "/operational-report")).json()
            assert not r["tax"]["invoices"]
            assert r["stock"]["summary"]["current_cost_value"] == 6000
            person = await c.post(base + "/customers", json={"name": "راھیل احمد"})
            assert person.status_code == 201, person.text
            customer_id = person.json()["id"]
            pdf = await c.get(
                base + f"/customers/{customer_id}/statement.pdf?language=ur"
            )
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            assert (
                await c.get(
                    base + f"/customers/{customer_id}/statement.pdf?language=xx"
                )
            ).status_code == 422
            assert (
                await c.get(
                    f"/api/v1/tenants/{other}/customers/{customer_id}/statement.pdf?language=ur"
                )
            ).status_code == 404
            email = uuid.uuid4().hex + "@example.com"
            await post(
                "member",
                tenant,
                email=email,
                name="Cashier",
                password="CashierPassword2026!",
                role="Cashier",
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as cashier:
                assert (
                    await cashier.post(
                        "/api/auth/login",
                        json=dict(email=email, password="CashierPassword2026!"),
                    )
                ).status_code == 200
                assert (
                    await cashier.get(base + "/operational-report")
                ).status_code == 403
                assert (
                    await cashier.get(base + "/inventory-turnover")
                ).status_code == 403
                assert (
                    await cashier.get(base + "/report-export/products.xlsx")
                ).status_code == 403
                assert (
                    await cashier.get(base + "/report-export/turnover.pdf")
                ).status_code == 403
                assert (
                    await cashier.get(
                        f"/api/v1/tenants/{other}/report-export/products.xlsx"
                    )
                ).status_code in (403, 404)

                assert (
                    await cashier.get(f"/api/v1/tenants/{other}/operational-report")
                ).status_code in (403, 404)
