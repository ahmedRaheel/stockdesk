import os, uuid
import httpx, pytest
from fastapi import HTTPException
from app.api.imports import parse

HEADER = "sku,name,category_code,unit_code,barcode,price,cost,initial,reorder\n"


def test_csv_parser_money_and_shape():
    assert (
        parse(HEADER + "RICE,Rice,general,kg,00123,1.23,0.10,1.25,5\n")[0][2]["price"]
        == 123
    )
    for row in [
        "RICE,Rice,general,kg,00123,1.234,0,1,5\n",
        "RICE,Rice,general,kg,00123,NaN,0,1,5\n",
        "RICE,Rice,general,kg,00123,1,0,1\n",
    ]:
        with pytest.raises(HTTPException):
            parse(HEADER + row)


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_import_preview_atomicity_and_retries():
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
        ) as c:
            await c.post(
                "/api/auth/login",
                json={"email": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD},
            )
            tid = (
                await c.post(
                    "/api/workspace",
                    json={"action": "tenant", "name": "Import test", "currency": "PKR"},
                )
            ).json()["id"]
            base = f"/api/v1/tenants/{tid}"
            path = base + "/catalog-imports"
            text = (
                HEADER
                + "NEW-1,Product one,general,piece,00123,150,100,3,5\nNEW-2,Product two,general,kg,00456,170.50,90,1.25,5\n"
            )
            r = await c.post(path + "/preview", json={"csv_text": text})
            assert r.status_code == 200, r.text
            assert r.json()["count"] == 2
            assert (await c.get(base + "/products")).json()["items"] == []
            bad = text.replace("general,kg", "missing,kg")
            r = await c.post(path, json={"csv_text": bad, "request": uuid.uuid4().hex})
            assert r.status_code == 400, r.text
            assert (await c.get(base + "/products")).json()[
                "items"
            ] == []  # first line rolled back
            payload = {"csv_text": text, "request": uuid.uuid4().hex}
            r = await c.post(path, json=payload)
            assert r.status_code == 201, r.text
            ids = r.json()["product_ids"]
            assert len(ids) == 2
            assert (await c.post(path, json=payload)).json()["product_ids"] == ids
            assert (
                await c.post(path, json={**payload, "csv_text": text.replace("170.50", "171.50")})
            ).status_code == 409
            assert (
                await c.post(path, json={**payload, "request": uuid.uuid4().hex})
            ).status_code == 400
            products = (await c.get(base + "/products")).json()["items"]
            assert len(products) == 2
            assert (
                next(p for p in products if p["sku"] == "NEW-1")["barcode"] == "00123"
            )
            assert next(p for p in products if p["sku"] == "NEW-2")["stock"] == 1.25
            # Duplicate codes within a file cause rollback too.
            dup = (
                HEADER
                + "DUP-1,One,general,piece,00999,10,1,0,5\nDUP-2,Two,general,piece,00999,10,1,0,5\n"
            )
            assert (
                await c.post(path, json={"csv_text": dup, "request": uuid.uuid4().hex})
            ).status_code == 400
            assert len((await c.get(base + "/products")).json()["items"]) == 2
