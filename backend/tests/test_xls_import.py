"""Legacy binary Excel uses the same atomic catalog contract as CSV/XLSX."""

import base64, os, struct, uuid
import httpx, pytest
from fastapi import HTTPException
from xls_fixture import workbook, record, compound
from app.api.imports import COLUMNS
from app.features.xls_import import convert

ROW = ["001", "Tea چائے", "general", "piece", "001234567", 150.25, 100.0, 2, 5]


def encode(raw):
    return base64.b64encode(raw).decode()


def test_values_identifiers_unicode_and_compound_container():
    for ole in (False, True):
        result = convert(encode(workbook([COLUMNS, ROW], ole=ole)))
        assert (
            result["count"] == 1
            and "001,Tea چائے,general,piece,001234567,150.25,100,2,5"
            in result["csv_text"]
        )
        assert convert(encode(workbook([COLUMNS, ROW, []], ole=ole)))["count"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"not an excel file",
        workbook([COLUMNS, ROW], hidden=True),
        workbook(
            [COLUMNS, ROW],
            extra=record(
                0x0006, struct.pack("<HHH", 1, 5, 0) + struct.pack("<d", 42) + b"\0" * 8
            ),
        ),
        workbook([COLUMNS, ROW], extra=record(0x01AE, b"\0" * 4)),
        workbook([COLUMNS, ROW], extra=record(0x002F, b"\0" * 4)),
        compound(workbook([COLUMNS, ROW]), extra_name="_VBA_PROJECT"),
        workbook(
            [COLUMNS, ROW], extra=record(0x0203, struct.pack("<HHHd", 201, 0, 0, 1))
        ),
        workbook(
            [COLUMNS, ROW], extra=record(0x0203, struct.pack("<HHHd", 1, 9, 0, 1))
        ),
        workbook([COLUMNS, [123, *ROW[1:]]]),
        workbook([COLUMNS, [*ROW[:5], True, *ROW[6:]]]),
        workbook([COLUMNS, [*ROW[:5], float("nan"), *ROW[6:]]]),
        workbook([COLUMNS[::-1], ROW]),
        workbook([COLUMNS, ROW])[:-1],
        b"X" * 1_000_001,
    ],
)
def test_reject_untrusted_or_unsupported_workbooks(raw):
    with pytest.raises(HTTPException) as error:
        convert(encode(raw))
    assert error.value.status_code == 400


def test_invalid_encoding_and_shared_business_validation():
    with pytest.raises(HTTPException):
        convert("@@@")
    with pytest.raises(HTTPException):
        convert(encode(workbook([COLUMNS, [*ROW[:5], -1, *ROW[6:]]])))


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_xls_http_create_update_atomicity_permissions():
    from app import config, db
    from app.main import app

    config.ADMIN_EMAIL = "test-admin@example.com"
    config.ADMIN_PASSWORD = "TestAdminPassword!2026"
    config.APP_ORIGIN = "http://testserver"
    db.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    async with app.router.lifespan_context(app):
        args = dict(
            transport=httpx.ASGITransport(app=app),
            base_url=config.APP_ORIGIN,
            headers={"Origin": config.APP_ORIGIN},
        )
        async with httpx.AsyncClient(**args) as c, httpx.AsyncClient(**args) as cashier:
            await c.post(
                "/api/auth/login",
                json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
            )

            async def old(action, **kw):
                r = await c.post("/api/workspace", json=dict(action=action, **kw))
                assert r.status_code == 200, r.text
                return r.json()

            t = (await old("tenant", name="XLS QA", currency="PKR"))["id"]
            base = f"/api/v1/tenants/{t}/catalog-imports"

            async def post(path, data):
                r = await c.post(base + path, json=data)
                assert r.status_code in (200, 201), r.text
                return r.json()

            converted = await post(
                "/convert-xls",
                {"file_base64": encode(workbook([COLUMNS, ROW], ole=True))},
            )
            preview = await post(
                "/preview", {"csv_text": converted["csv_text"], "mode": "create"}
            )
            assert preview["count"] == 1
            payload = {
                "csv_text": converted["csv_text"],
                "mode": "create",
                "request": uuid.uuid4().hex,
            }
            saved = await post("", payload)
            assert await post("", payload) == saved
            changed = [*ROW]
            changed[5] = 160
            changed[7] = 0
            converted = await post(
                "/convert-xls",
                {"file_base64": encode(workbook([COLUMNS, changed], ole=True))},
            )
            preview = await post(
                "/preview", {"csv_text": converted["csv_text"], "mode": "update"}
            )
            await post(
                "",
                {
                    "csv_text": converted["csv_text"],
                    "mode": "update",
                    "request": uuid.uuid4().hex,
                    "preview_token": preview["preview_token"],
                },
            )
            async with db.pool.acquire() as conn:
                p = await conn.fetchrow("SELECT * FROM products WHERE tenant=$1", t)
                assert (
                    p["sku"] == "001"
                    and p["barcode"] == "001234567"
                    and p["price"] == 16000
                    and p["stock"] == 2
                )
            # A duplicate SKU or bad reference must not create any part of a batch.
            second = ["NEW", "New", "missing-category", "piece", "", 10, 5, 1, 0]
            converted = await post(
                "/convert-xls", {"file_base64": encode(workbook([COLUMNS, second]))}
            )
            denied = await c.post(
                base,
                json={
                    "csv_text": converted["csv_text"],
                    "request": uuid.uuid4().hex,
                    "mode": "create",
                },
            )
            assert denied.status_code in (400, 404, 409)
            async with db.pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM products WHERE tenant=$1", t
                    )
                    == 1
                )
            email = uuid.uuid4().hex + "@example.com"
            await old(
                "member",
                tenant=t,
                email=email,
                name="Cashier",
                role="Cashier",
                password="CashierPassword2026!",
            )
            await cashier.post(
                "/api/auth/login",
                json={"email": email, "password": "CashierPassword2026!"},
            )
            upload = {"file_base64": encode(workbook([COLUMNS, ROW]))}
            assert (
                await cashier.post(base + "/convert-xls", json=upload)
            ).status_code == 403
            assert (
                await c.post(
                    base + "/convert-xls",
                    json=upload,
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
