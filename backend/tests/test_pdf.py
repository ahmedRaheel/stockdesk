from datetime import datetime, timezone
from app.pdf import invoice_pdf, barcode_pdf


def test_invoice_and_barcode_pdf():
    sale = dict(
        seller_name="Example Store",
        seller_address="Karachi",
        seller_tax_number="",
        invoice_number="INV-0000001",
        created=datetime.now(timezone.utc),
        customer="Customer <sample>",
        status="completed",
        subtotal=10000,
        discount=1000,
        tax_bps=1800,
        tax=1620,
        total=10620,
        payment="cash",
        actor="cashier@example.com",
        currency="PKR",
    )
    lines = [dict(name="Keyboard & mouse", sku="KB-1", quantity=1, price=10000)]
    assert invoice_pdf(sale, lines).startswith(b"%PDF")
    assert invoice_pdf(sale, lines * 90).startswith(b"%PDF")
    import json

    sale["promotion_snapshot"] = json.dumps(
        dict(code="TEA-10", name="Tea <offer>", name_ur="چائے کی پیشکش")
    )
    assert invoice_pdf(sale, lines, "ur").startswith(b"%PDF")
    assert barcode_pdf(
        {"name": "Keyboard", "barcode": "123456789012", "sku": "KB-1"}
    ).startswith(b"%PDF")


def test_urdu_statement_and_multipage_rows():
    from app.pdf import customer_statement_pdf

    data = dict(
        customer=dict(name="راھیل احمد <sample>"),
        balance=15000,
        entries=[
            dict(
                created="2026-10-25",
                kind="sale",
                reference="INV-0001",
                amount=20000,
                balance=20000,
            ),
            dict(
                created="2026-10-25",
                kind="recovery",
                reference="وصولی & PKR",
                amount=-5000,
                balance=15000,
            ),
        ],
    )
    for language in ["en", "ur"]:
        assert customer_statement_pdf(
            data, dict(name="نمونہ دکان", currency="PKR"), language
        ).startswith(b"%PDF")
    data["entries"] *= 50
    pdf = customer_statement_pdf(data, dict(name="نمونہ دکان", currency="PKR"), "ur")
    assert pdf.startswith(b"%PDF") and len(pdf) > 10000
