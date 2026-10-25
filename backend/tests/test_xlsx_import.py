from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import base64
import xml.etree.ElementTree as ET
import os
import uuid
import pytest
import httpx
from fastapi import HTTPException
from app.features.xlsx_import import convert

TEMPLATE = Path(__file__).resolve().parents[1] / "app/templates/catalog-template.xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def encoded(data=None):
    return base64.b64encode(TEMPLATE.read_bytes() if data is None else data).decode()


def altered(sheet_change=None, extra=None, strings=None):
    out = BytesIO()
    with ZipFile(TEMPLATE) as source, ZipFile(out, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if sheet_change and name == "xl/worksheets/sheet1.xml":
                tree = ET.fromstring(data)
                sheet_change(tree)
                data = ET.tostring(tree)
            if strings and name in {"xl/sharedStrings.xml", "xl/worksheets/sheet1.xml"}:
                data = data.replace(*strings)
            target.writestr(name, data)
        if extra:
            target.writestr(*extra)
    return out.getvalue()


def cell(tree, ref):
    return next(c for c in tree.iter(NS + "c") if c.attrib["r"] == ref)


def test_excel_template_and_identifiers():
    r = convert(encoded())
    assert r["count"] == 1 and "SAMPLE-001" in r["csv_text"]
    raw = altered(strings=(b"BAR-001234567", b"001234567"))
    assert ",001234567," in convert(encoded(raw))["csv_text"]

    def dimensions(tree):
        ET.SubElement(tree, NS + "dimension", {"ref": "A1:XFD1048576"})

    assert convert(encoded(altered(sheet_change=dimensions)))["count"] == 1


def test_excel_rejects_formula_numeric_identifiers_and_outside_rows():
    def formula(tree):
        c = cell(tree, "F2")
        c.clear()
        c.set("r", "F2")
        ET.SubElement(c, NS + "f").text = "1+1"
        ET.SubElement(c, NS + "v").text = "2"

    def numeric(tree):
        c = cell(tree, "E2")
        c.clear()
        c.set("r", "E2")
        c.set("t", "n")
        ET.SubElement(c, NS + "v").text = "123"

    def outside(tree):
        cell(tree, "E2").set("r", "XFD2")

    def overflow(tree):
        cell(tree, "E2").set("r", "E202")

    for mutate in [formula, numeric, outside, overflow]:
        with pytest.raises(HTTPException):
            convert(encoded(altered(sheet_change=mutate)))
    with pytest.raises(HTTPException):
        convert("not-base64!")
    with pytest.raises(HTTPException):
        convert(encoded(b"not-an-excel-file"))
    with pytest.raises(HTTPException):
        convert(encoded(altered(extra=("xl/vbaProject.bin", b"macro"))))
    with pytest.raises(HTTPException):
        convert(encoded(altered(extra=("xl/externalLinks/externalLink1.xml", b"link"))))
    with pytest.raises(HTTPException):
        convert(encoded(altered(extra=("padding.txt", b"0" * 8_000_001))))


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_excel_api_preview_atomic_import_and_access():
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
                    json=dict(email=config.ADMIN_EMAIL, password=config.ADMIN_PASSWORD),
                )
            ).status_code == 200
            r = await c.post(
                "/api/workspace",
                json=dict(action="tenant", name="Excel imports", currency="PKR"),
            )
            assert r.status_code == 200
            t = r.json()["id"]
            base = f"/api/v1/tenants/{t}"
            path = base + "/catalog-imports"
            template = await c.get(path + "/template.xlsx")
            assert (
                template.status_code == 200
                and template.content == TEMPLATE.read_bytes()
            )
            converted = await c.post(
                path + "/convert-xlsx", json=dict(file_base64=encoded(template.content))
            )
            assert converted.status_code == 200, converted.text
            text = converted.json()["csv_text"]
            assert (await c.get(base + "/products")).json()["items"] == []
            assert (
                await c.post(path + "/preview", json=dict(csv_text=text))
            ).status_code == 200
            assert (await c.get(base + "/products")).json()["items"] == []
            payload = dict(csv_text=text, request=uuid.uuid4().hex)
            imported = await c.post(path, json=payload)
            assert imported.status_code == 201, imported.text
            assert (await c.post(path, json=payload)).json()[
                "product_ids"
            ] == imported.json()["product_ids"]
            assert len((await c.get(base + "/products")).json()["items"]) == 1
            email = uuid.uuid4().hex + "@example.com"
            assert (
                await c.post(
                    "/api/workspace",
                    json=dict(
                        action="member",
                        tenant=t,
                        email=email,
                        name="Cashier",
                        password="CashierPassword2026!",
                        role="Cashier",
                    ),
                )
            ).status_code == 200
            async with httpx.AsyncClient(
                transport=transport,
                base_url=config.APP_ORIGIN,
                headers={"Origin": config.APP_ORIGIN},
            ) as cash:
                await cash.post(
                    "/api/auth/login",
                    json=dict(email=email, password="CashierPassword2026!"),
                )
                assert (await cash.get(path + "/template.xlsx")).status_code == 403
                assert (
                    await cash.post(
                        path + "/convert-xlsx", json=dict(file_base64=encoded())
                    )
                ).status_code == 403
