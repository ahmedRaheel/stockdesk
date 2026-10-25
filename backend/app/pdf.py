"""Paginated invoice PDFs and printable Code128 labels. Text is escaped."""

from io import BytesIO
from decimal import Decimal
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.graphics.barcode import code128
from reportlab.pdfgen import canvas

FONT_DIR = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("StockDesk", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("StockDeskBold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

pdfmetrics.registerFont(TTFont("StockDeskUrdu", str(FONT_DIR / "NotoNaskhArabic.ttf")))
pdfmetrics.registerFont(
    TTFont("StockDeskUrduBold", str(FONT_DIR / "NotoNaskhArabicBold.ttf"))
)


def invoice_pdf(sale, items, language="en", tenders=None):
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    import re

    labels = {
        "Split payment": "مختلف طریقوں سے ادائیگی",
        "cash": "نقد",
        "external": "بیرونی ادائیگی",
        "Kilogram": "کلوگرام",
        "Piece": "عدد",
        "Litre": "لیٹر",
        "Dozen": "درجن",
        "Pack": "پیکٹ",
        "Walk-in customer": "عام گاہک",
        "COMPLETED": "مکمل",
        "RETURNED": "واپس شدہ",
        "Tax ID": "ٹیکس نمبر",
        "INVOICE": "رسید",
        "Date": "تاریخ",
        "Customer": "گاہک",
        "Status": "حالت",
        "Product / SKU": "مصنوعات / SKU",
        "Qty": "مقدار",
        "Unit price": "فی اکائی قیمت",
        "Amount": "رقم",
        "Subtotal": "ذیلی مجموعہ",
        "Discount": "رعایت",
        "Tax added": "اضافی ٹیکس",
        "Tax included in prices": "قیمتوں میں شامل ٹیکس",
        "TOTAL": "کل",
        "Paid now": "اب وصول شدہ",
        "Khata credit": "کھاتہ ادھار",
        "Payment": "ادائیگی",
        "Cash": "نقد",
        "Collected externally": "بیرونی وصولی",
        "Served by": "فروخت کنندہ",
        "Thank you for your business.": "آپ کی خریداری کا شکریہ۔",
        "RETURNED — stock restored. Refund payment must be completed separately.": "واپس شدہ — اسٹاک بحال ہو گیا۔ رقم الگ واپس کریں۔",
    }

    def label(value):
        return labels.get(value, value) if language == "ur" else value

    def shape(value):
        value = str(value)
        return (
            get_display(reshape(value))
            if re.search("[\u0600-\u06ff]", value)
            else value
        )

    buf = BytesIO()
    styles = getSampleStyleSheet()
    for name in styles.byName:
        styles[name].fontName = (
            "StockDeskBold"
            if name in ["Title", "Heading1", "Heading2", "Heading3"]
            else "StockDesk"
        )
    if language == "ur":
        for style in styles.byName.values():
            style.alignment = 2
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=45
    )

    def p(value, style="Normal"):
        value = str(value)
        if re.search("[\u0600-\u06ff]", value):
            font = (
                "StockDeskUrduBold"
                if style in ["Title", "Heading1", "Heading2", "Heading3"]
                else "StockDeskUrdu"
            )
            # Render Arabic runs using the bundled font; retain Latin/numbers with DejaVu.
            shaped = shape(value)
            chunks = re.split("([\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff]+)", shaped)
            html = "".join(
                (
                    '<font name="' + font + '">' + escape(x) + "</font>"
                    if re.search("[\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff]", x)
                    else escape(x)
                )
                for x in chunks
            )
            return Paragraph(html, styles[style])
        return Paragraph(escape(value), styles[style])

    def money(n):
        return f"{sale['currency']} {n/100:,.2f}"

    story = [
        p(sale["seller_name"], "Title"),
        p(sale["seller_address"]),
        p(
            label("Tax ID") + ": " + sale["seller_tax_number"]
            if sale["seller_tax_number"]
            else ""
        ),
        Spacer(1, 20),
        p(label("INVOICE") + " " + sale["invoice_number"], "Heading1"),
        p(label("Date") + ": " + sale["created"].strftime("%Y-%m-%d %H:%M UTC")),
        p(label("Customer") + ": " + label(sale["customer"])),
        p(label("Status") + ": " + label(sale["status"].upper())),
        Spacer(1, 18),
    ]
    rows = [
        [
            p(label("Product / SKU")),
            p(label("Qty")),
            p(label("Unit price")),
            p(label("Amount")),
        ]
    ]
    for i in items:
        rows.append(
            [
                p(i["name"] + " / " + i["sku"]),
                p(
                    format(
                        Decimal(str(i["quantity"])).normalize(),
                        "f",
                    )
                    + " "
                    + label(i.get("unit_name", ""))
                ),
                money(i["price"]),
                money(i.get("line_total", i["quantity"] * i["price"])),
            ]
        )
    table = Table(rows, colWidths=[195, 80, 110, 110], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "StockDesk"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2ed")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#9bb9a7")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dfe6e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story += [table, Spacer(1, 20)]
    for caption, value in [
        ("Subtotal", sale["subtotal"]),
        ("Discount", -sale["discount"]),
        ("Tax added", sale["tax"] - sale.get("tax_included", 0)),
        ("Tax included in prices", sale.get("tax_included", 0)),
        ("TOTAL", sale["total"]),
        ("Paid now", sale.get("paid_now", sale["total"])),
        ("Khata credit", sale.get("credit_amount", 0)),
    ]:
        story.append(
            p(
                label(caption) + ": " + money(value),
                "Heading3" if caption == "TOTAL" else "Normal",
            )
        )
    story += [
        Spacer(1, 16),
        p(
            label("Payment")
            + ": "
            + label(
                "Split payment"
                if len(tenders or []) > 1
                else "Cash" if sale["payment"] == "cash" else "Collected externally"
            )
        ),
        p(label("Served by") + ": " + sale["actor"]),
        Spacer(1, 16),
        p(label("Thank you for your business.")),
    ]
    for part in tenders or []:
        name = part.get("method_name_ur") if language == "ur" else part["method_name"]
        story.append(
            p(label(name or part["method_name"]) + ": " + money(part["amount"]))
        )
    if sale["status"] == "returned":
        story.append(
            p(
                label(
                    "RETURNED — stock restored. Refund payment must be completed separately."
                )
            )
        )

    def footer(c, d):
        c.saveState()
        c.setFont("StockDesk", 8)
        c.setFillColor(colors.grey)
        c.drawString(40, 25, sale["invoice_number"])
        c.drawRightString(A4[0] - 40, 25, f"Page {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def barcode_pdf(product):
    value = product["barcode"] or product["sku"]
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(300, 140))
    c.setFont("StockDeskBold", 10)
    c.drawCentredString(150, 120, product["name"][:45])
    b = code128.Code128(
        value, barHeight=48, barWidth=0.8, humanReadable=True, fontName="StockDesk"
    )
    scale = min(1, 270 / b.width)
    c.saveState()
    c.translate((300 - b.width * scale) / 2, 45)
    c.scale(scale, 1)
    b.drawOn(c, 0, 0)
    c.restoreState()
    c.setFont("StockDesk", 8)
    c.drawCentredString(150, 18, product["sku"])
    c.save()
    return buf.getvalue()


def customer_statement_pdf(data, business, language="en"):
    """Bilingual account statement with shaped Urdu and a running balance."""
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4

    output = BytesIO()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "StockDesk"
    import re
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display

    labels = {
        "Customer statement": "گاہک کا کھاتہ",
        "Outstanding": "بقایا رقم",
        "Date": "تاریخ",
        "Entry / reference": "اندراج / حوالہ",
        "Debit": "واجب الادا",
        "Credit": "وصول شدہ",
        "Balance": "بقایا",
        "sale": "فروخت",
        "recovery": "وصولی",
        "markup": "اضافی رقم",
        "payment": "ادائیگی",
        "return": "واپسی",
        "opening": "ابتدائی بقایا",
        "adjustment": "درستگی",
        "writeoff": "معاف شدہ رقم",
    }
    label = lambda value: labels.get(value, value) if language == "ur" else value
    for style in styles.byName.values():
        style.leading = 17
        if language == "ur":
            style.alignment = 2

    def text(value):
        value = str(value)
        if re.search("[\u0600-\u06ff]", value):
            shaped = get_display(reshape(value))
            chunks = re.split("([\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff]+)", shaped)
            value = "".join(
                (
                    '<font name="StockDeskUrdu">' + escape(x) + "</font>"
                    if re.search("[\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff]", x)
                    else escape(x)
                )
                for x in chunks
            )
        else:
            value = escape(value)
        return Paragraph(value, styles["BodyText"])

    money = lambda value: f"{business['currency']} {value/100:,.2f}"
    flow = [
        text(business["name"]),
        Spacer(1, 12),
        text(label("Customer statement") + " / " + data["customer"]["name"]),
        text(label("Outstanding") + ": " + money(data["balance"])),
        Spacer(1, 12),
    ]
    table = [
        [
            text(label(x))
            for x in ["Date", "Entry / reference", "Debit", "Credit", "Balance"]
        ]
    ]
    for row in data["entries"]:
        table.append(
            [
                text(str(row["created"])[:10]),
                text(label(row["kind"]) + " / " + row["reference"]),
                text(money(row["amount"]) if row["amount"] > 0 else ""),
                text(money(-row["amount"]) if row["amount"] < 0 else ""),
                text(money(row["balance"])),
            ]
        )
    widths = [83, 142, 92, 92, 92]
    if language == "ur":
        table = [list(reversed(row)) for row in table]
        widths.reverse()
    widget = Table(table, colWidths=widths, repeatRows=1)
    widget.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dfe3e8")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    flow.append(widget)
    SimpleDocTemplate(output, pagesize=A4, leftMargin=30, rightMargin=30).build(flow)
    return output.getvalue()
