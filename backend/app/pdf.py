"""Paginated invoice PDFs and printable Code128 labels. Text is escaped."""

from io import BytesIO
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


def invoice_pdf(sale, items):
    buf = BytesIO()
    styles = getSampleStyleSheet()
    for name in styles.byName:
        styles[name].fontName = (
            "StockDeskBold"
            if name in ["Title", "Heading1", "Heading2", "Heading3"]
            else "StockDesk"
        )
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=45
    )

    def p(value, style="Normal"):
        return Paragraph(escape(str(value)), styles[style])

    def money(n):
        return f"{sale['currency']} {n/100:,.2f}"

    story = [
        p(sale["seller_name"], "Title"),
        p(sale["seller_address"]),
        p("Tax ID: " + sale["seller_tax_number"] if sale["seller_tax_number"] else ""),
        Spacer(1, 20),
        p("INVOICE " + sale["invoice_number"], "Heading1"),
        p("Date: " + sale["created"].strftime("%Y-%m-%d %H:%M UTC")),
        p("Customer: " + sale["customer"]),
        p("Status: " + sale["status"].upper()),
        Spacer(1, 18),
    ]
    rows = [[p("Product / SKU"), p("Qty"), p("Unit price"), p("Amount")]]
    for i in items:
        rows.append(
            [
                p(i["name"] + " / " + i["sku"]),
                str(i["quantity"]),
                money(i["price"]),
                money(i["quantity"] * i["price"]),
            ]
        )
    table = Table(rows, colWidths=[235, 40, 110, 110], repeatRows=1, hAlign="LEFT")
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
    for label, value in [
        ("Subtotal", sale["subtotal"]),
        ("Discount", -sale["discount"]),
        (f"Tax ({sale['tax_bps']/100:g}%)", sale["tax"]),
        ("TOTAL", sale["total"]),
    ]:
        story.append(
            p(label + ": " + money(value), "Heading3" if label == "TOTAL" else "Normal")
        )
    story += [
        Spacer(1, 16),
        p(
            "Payment: "
            + ("Cash" if sale["payment"] == "cash" else "Collected externally")
        ),
        p("Served by: " + sale["actor"]),
        Spacer(1, 16),
        p("Thank you for your business."),
    ]
    if sale["status"] == "returned":
        story.append(
            p("RETURNED — stock restored. Refund payment must be completed separately.")
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
