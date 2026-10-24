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
    assert barcode_pdf(
        {"name": "Keyboard", "barcode": "123456789012", "sku": "KB-1"}
    ).startswith(b"%PDF")
