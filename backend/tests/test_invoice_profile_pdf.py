from datetime import datetime, timezone

from app.pdf import invoice_pdf


def test_invoice_profile_renders_thermal_business_details():
    sale = {
        "seller_name": "Nimco Food N Snacks",
        "seller_address": "Shop 2 & 3, Jilani Homes, Karachi",
        "seller_tax_number": "legacy-tax-id",
        "invoice_number": "INV-0000001",
        "created": datetime(2026, 10, 29, 20, 11, tzinfo=timezone.utc),
        "customer": "Anonymous",
        "status": "completed",
        "currency": "PKR",
        "subtotal": 91000,
        "discount": 0,
        "tax": 16380,
        "total": 107380,
        "paid_now": 107380,
        "payment": "cash",
        "actor": "cashier@example.com",
        "tendered": 110000,
        "cash_amount": 107380,
        "seller_profile": {
            "branch_name": "Dhoraji Branch",
            "shop_number": "2 & 3",
            "phone": "021-34188200",
            "ntn": "6978535-7",
            "strn": "423017546175",
            "invoice_title": "CASH INVOICE",
            "receipt_width": "80mm",
            "return_policy": "No return without receipt.",
            "exchange_policy": "Dry items exchange only.",
        },
    }
    items = [
        {"name": "Masala Puffs", "sku": "MP", "quantity": 1, "price": 22000, "line_total": 22000},
        {"name": "Potato Crisps", "sku": "PC", "quantity": 1, "price": 24000, "line_total": 24000},
        {"name": "Special Mix 400g", "sku": "SM", "quantity": 1, "price": 45000, "line_total": 45000},
    ]

    result = invoice_pdf(sale, items)

    assert result.startswith(b"%PDF-")
    assert len(result) > 1000
