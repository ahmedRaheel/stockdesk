import os
import uuid
from datetime import timedelta
import httpx
import pytest
from pydantic import ValidationError
from app.api.report_builder import Definition, build


def test_builder_contract_and_selection():
    for values in [
        dict(columns=["cost", "cost"]),
        dict(columns=["password"]),
        dict(columns=["sku"], sort="secret"),
        dict(columns=["sku"], days=True),
        dict(columns=["sku"], limit=5001),
    ]:
        with pytest.raises(ValidationError):
            Definition(**values)
    data = dict(
        products=[
            dict(sku="A", name="Alpha", net_sales=100, margin_pct=None),
            dict(sku="B", name="Beta", net_sales=200, margin_pct=20),
            dict(sku="C", name="Zero", net_sales=0, margin_pct=None),
        ],
        start="2026-01-01",
        end="2026-01-30",
        timezone="Asia/Karachi",
        currency="PKR",
        business="Test",
    )
    r = build(data, Definition(columns=["sku", "net_sales"], hide_zero=True, limit=1))
    assert (
        r["rows"] == [dict(sku="B", net_sales=200)]
        and r["matching_rows"] == 2
        and r["truncated"]
    )
    assert build(
        data, Definition(columns=["sku"], sort="margin_pct", descending=False)
    )["rows"] == [{"sku": "B"}, {"sku": "A"}, {"sku": "C"}]
    assert build(data, Definition(columns=["sku"], search="alpha"))["rows"] == [
        dict(sku="A")
    ]


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_builder_authorized_data_saved_views_and_dates():
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

            async def post(path, data, status=200):
                r = await c.post(path, json=data)
                assert r.status_code == status, r.text
                return r.json()

            await post(
                "/api/auth/login",
                dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )
            tenant = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Report builder", currency="PKR"),
                )
            )["id"]
            other = (
                await post(
                    "/api/workspace",
                    dict(action="tenant", name="Other reports", currency="PKR"),
                )
            )["id"]
            base = f"/api/v1/tenants/{tenant}"
            url = base + "/report-builder"
            pid = (
                await post(
                    base + "/products",
                    dict(
                        sku="COFFEE",
                        name="Coffee",
                        category="General",
                        price=1000,
                        cost=400,
                        initial=20,
                    ),
                    201,
                )
            )["id"]
            await post(base + "/tills", dict(opening_cash=0))
            sale = (
                await post(
                    base + "/sales",
                    dict(
                        request=uuid.uuid4().hex,
                        items=[dict(id=pid, quantity=2)],
                        payment="cash",
                        expected=2000,
                        tendered=2000,
                    ),
                )
            )["id"]
            yesterday = business_date() - timedelta(days=1)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE sales SET created=($1::date::timestamp AT TIME ZONE 'Asia/Karachi')+interval '12 hours' WHERE id=$2",
                    yesterday,
                    sale,
                )
            definition = dict(
                group="products",
                columns=["sku", "net_sales", "cost", "profit"],
                days=1,
                hide_zero=True,
            )
            result = await post(url + "/run", definition)
            assert result["rows"] == [
                dict(sku="COFFEE", net_sales=2000, cost=800, profit=1200)
            ]
            assert result["start"] == str(yesterday) and result["end"] == str(yesterday)
            assert (
                await post(
                    url + "/run",
                    {**definition, "end": str(yesterday - timedelta(days=1))},
                )
            )["rows"] == []
            await post(url + "/run", {**definition, "end": str(business_date())}, 400)
            await post(url + "/run", {**definition, "end": "0001-01-01"}, 400)
            assert (
                await post(f"/api/v1/tenants/{other}/report-builder/run", definition)
            )["rows"] == []
            body = dict(
                id=uuid.uuid4().hex,
                name="Daily margin",
                definition=definition,
                version=0,
            )
            r = await c.put(url + "/views", json=body)
            assert r.status_code == 200, r.text
            assert (await c.put(url + "/views", json=body)).json()["replayed"]
            r = await c.put(
                url + "/views", json={**body, "version": 1, "name": "Updated margin"}
            )
            assert r.status_code == 200
            assert (
                await c.put(
                    url + "/views", json={**body, "version": 1, "name": "Stale"}
                )
            ).status_code == 409
            view = (await c.get(url + "/views")).json()["items"][0]
            assert view["version"] == 2
            assert (
                await c.get(f"/api/v1/tenants/{other}/report-builder/views")
            ).json()["items"] == []
            email = uuid.uuid4().hex + "@example.com"
            password = "CashierPassword2026!"
            await post(
                "/api/workspace",
                dict(
                    action="member",
                    tenant=tenant,
                    email=email,
                    password=password,
                    name="Report cashier",
                    role="Cashier",
                ),
            )
            await cashier.post(
                "/api/auth/login", json=dict(email=email, password=password)
            )
            assert (await cashier.get(url + "/views")).status_code == 403
            assert (
                await cashier.post(url + "/run", json=definition)
            ).status_code == 403
            assert (await cashier.put(url + "/views", json=body)).status_code == 403
            assert (
                await c.post(
                    url + "/run",
                    json=definition,
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            assert (
                await c.delete(url + "/views/" + body["id"] + "?version=1")
            ).status_code == 409
            assert (
                await c.delete(url + "/views/" + body["id"] + "?version=2")
            ).status_code == 200
            assert (
                await c.delete(url + "/views/" + body["id"] + "?version=2")
            ).status_code == 200
            assert (await c.get(url + "/views")).json()["items"] == []
            for query in [
                "event_pct=301",
                "event_start=30&event_days=2",
                "event_days=0",
            ]:
                assert (
                    await c.get("/api/forecasts?tenant=" + tenant + "&" + query)
                ).status_code == 400
