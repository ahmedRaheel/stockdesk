"""Paginated invoice PDFs and printable Code128 labels. Text is escaped."""

from io import BytesIO
from decimal import Decimal
from datetime import datetime
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


def _register_optional_font(name, paths, fallback):
    # Do not distribute binary font assets with source. Docker installs distro fonts.
    for candidate in paths:
        path = Path(candidate)
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    return fallback


FONT_REGULAR = _register_optional_font("StockDesk", [
    FONT_DIR / "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
], "Helvetica")
FONT_BOLD = _register_optional_font("StockDeskBold", [
    FONT_DIR / "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
], "Helvetica-Bold")
FONT_URDU = _register_optional_font("StockDeskUrdu", [
    FONT_DIR / "NotoNaskhArabic.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
], FONT_REGULAR)
FONT_URDU_BOLD = _register_optional_font("StockDeskUrduBold", [
    FONT_DIR / "NotoNaskhArabicBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
], FONT_BOLD)


def invoice_pdf(sale, items, language="en", tenders=None):
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    import re

    labels = {
        "Original collection": "اصل وصولی",
        "Invoice revision": "رسید کی ترمیم",
        "Retained payment": "باقی اشیاء کی ادا شدہ رقم",
        "Khata debt reduction": "کھاتے کے قرض میں کمی",
        "Financing balance waived": "معاف کردہ فنانسنگ بقایا",
        "Remaining invoice debt": "بل کا باقی قرض",
        "Return credit": "واپسی کی قیمت",
        "Collected from customer": "گاہک سے وصول شدہ",
        "Refunded to customer": "گاہک کو واپس کردہ",
        "No payment difference": "رقم میں کوئی فرق نہیں",
        "Replacement invoice": "متبادل کی رسید",
        "Payment details are the original collection. Adjustments are listed separately.": "ادائیگی کی تفصیل اصل وصولی کی ہے۔ تبدیلیاں الگ درج ہیں۔",
        "Returned items and settlement recorded in adjustment history.": "واپس شدہ اشیاء اور ادائیگی تبدیلی کی تاریخ میں درج ہیں۔",
        "expired": "میعاد ختم",
        "damaged": "خراب",
        "incorrect": "غلط",
        "opened": "کھلی ہوئی",
        "Cash received": "وصول شدہ نقد رقم",
        "Change returned": "گاہک کو واپس کی گئی رقم",
        "Promotion": "رعایتی پیشکش",
        "Return all remaining qualifying and reward product quantities together for this cross-product offer.": "اس مختلف مصنوعات کی پیشکش میں خریدی گئی اور انعامی مصنوعات کی تمام باقی مقدار ایک ساتھ واپس کریں۔",
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

    profile = sale.get("seller_profile") or {}
    if isinstance(profile, str):
        import json
        profile = json.loads(profile)
    from reportlab.lib.units import mm
    receipt_width = profile.get("receipt_width", "A4")
    if receipt_width == "58mm":
        page_size = (58 * mm, 260 * mm)
        margins = (5 * mm, 5 * mm, 6 * mm, 6 * mm)
    elif receipt_width == "80mm":
        page_size = (80 * mm, 300 * mm)
        margins = (5 * mm, 5 * mm, 6 * mm, 6 * mm)
    else:
        page_size = A4
        margins = (40, 40, 40, 45)
    buf = BytesIO()
    styles = getSampleStyleSheet()
    for name in styles.byName:
        styles[name].fontName = (
            FONT_BOLD
            if name in ["Title", "Heading1", "Heading2", "Heading3"]
            else FONT_REGULAR
        )
    if language == "ur":
        for style in styles.byName.values():
            style.alignment = 2
    doc = SimpleDocTemplate(
        buf, pagesize=page_size, rightMargin=margins[0], leftMargin=margins[1],
        topMargin=margins[2], bottomMargin=margins[3]
    )

    def p(value, style="Normal"):
        value = str(value)
        if re.search("[\u0600-\u06ff]", value):
            font = (
                FONT_URDU_BOLD
                if style in ["Title", "Heading1", "Heading2", "Heading3"]
                else FONT_URDU
            )
            # Use the configured system Arabic font for the Arabic runs.
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

    story = [p(sale["seller_name"], "Title")]
    if profile.get("branch_name"):
        story.append(p(profile["branch_name"], "Heading2"))
    if profile.get("shop_number"):
        story.append(p("Shop: " + profile["shop_number"]))
    if sale.get("seller_address"):
        story.append(p(sale["seller_address"]))
    contact = "  |  ".join(x for x in (profile.get("phone"), profile.get("email"), profile.get("website")) if x)
    if contact:
        story.append(p(contact))
    registrations = []
    if profile.get("ntn"):
        registrations.append("NTN: " + profile["ntn"])
    if profile.get("strn"):
        registrations.append("STRN: " + profile["strn"])
    if sale.get("seller_tax_number") and not registrations:
        registrations.append(label("Tax ID") + ": " + sale["seller_tax_number"])
    if registrations:
        story.append(p("  |  ".join(registrations)))
    if profile.get("invoice_header"):
        story.append(p(profile["invoice_header"]))
    story += [
        Spacer(1, 12),
        p(profile.get("invoice_title") or label("INVOICE"), "Heading1"),
        p(label("INVOICE") + " " + sale["invoice_number"], "Heading2"),
        p(
            label("Date")
            + ": "
            + (
                datetime.fromisoformat(sale["created"])
                if isinstance(sale["created"], str)
                else sale["created"]
            ).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Karachi")).strftime("%A, %B %d, %Y %I:%M %p")
        ),
        p(label("Customer") + ": " + label(sale["customer"])),
        p(label("Status") + ": " + label(sale["status"].upper())),
        Spacer(1, 18),
    ]
    thermal = receipt_width in ("58mm", "80mm")
    rows = [[p("Item"), p("Qty"), p("Price"), p("GST"), p("Amount")]]
    item_amounts = [
        int(i.get("line_total") or Decimal(str(i["quantity"])) * i["price"])
        for i in items
    ]
    taxable_base = sum(item_amounts) or 1
    allocated_tax = 0
    for index, i in enumerate(items):
        amount = item_amounts[index]
        line_tax = (
            int(sale.get("tax", 0)) - allocated_tax
            if index == len(items) - 1
            else round(int(sale.get("tax", 0)) * amount / taxable_base)
        )
        allocated_tax += line_tax
        quantity = format(Decimal(str(i["quantity"])).normalize(), "f")
        if thermal:
            rows.append([
                p(i["name"] + " / " + i["sku"]),
                p(quantity),
                p(money(i["price"])),
                p(money(line_tax)),
                p(money(amount)),
            ])
        else:
            rows.append([
                p(i["name"] + " / " + i["sku"]),
                p(quantity + " " + label(i.get("unit_name", ""))),
                p(money(i["price"])),
                p(money(line_tax)),
                p(money(amount)),
            ])
    available_width = page_size[0] - margins[0] - margins[1]
    if thermal:
        widths = [available_width * .36, available_width * .10, available_width * .18, available_width * .16, available_width * .20]
    else:
        widths = [available_width * .32, available_width * .13, available_width * .18, available_width * .17, available_width * .20]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
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
        (
            "Retained payment" if sale.get("revision") else "Paid now",
            sale.get("paid_now", sale["total"]),
        ),
        ("Khata credit", sale.get("credit_amount", 0)),
    ]:
        story.append(
            p(
                label(caption) + ": " + money(value),
                "Heading3" if caption == "TOTAL" else "Normal",
            )
        )
    if sale.get("revision"):
        story.append(
            p(label("Invoice revision") + ": " + str(sale["revision"]), "Heading3")
        )
        story.append(
            p(
                label(
                    "Payment details are the original collection. Adjustments are listed separately."
                )
            )
        )
        for adjustment in sale.get("adjustments", []):
            for returned in adjustment["returns"]:
                story.append(
                    p(
                        returned["name"]
                        + " / "
                        + str(returned["quantity"])
                        + " / "
                        + label(returned["reason"])
                    )
                )
            story.append(p(label("Return credit") + ": " + money(adjustment["credit"])))
            if adjustment.get("outstanding_before", 0):
                for caption, key in (
                    ("Khata debt reduction", "debt_credit"),
                    ("Financing balance waived", "debt_waiver"),
                    ("Remaining invoice debt", "outstanding_after"),
                ):
                    story.append(p(label(caption) + ": " + money(adjustment[key])))
            caption = (
                "Collected from customer"
                if adjustment["net"] > 0
                else (
                    "Refunded to customer"
                    if adjustment["net"] < 0
                    else "No payment difference"
                )
            )
            story.append(p(label(caption) + ": " + money(abs(adjustment["net"]))))
            story.append(p(adjustment["id"] + " / " + adjustment["settlement"]))
            for refund in adjustment.get("refunds", []):
                name = refund.get("name_ur") if language == "ur" else refund["name"]
                story.append(
                    p(
                        (name or refund["name"])
                        + ": "
                        + money(refund["amount"])
                        + " / "
                        + refund.get("settlement_reference", "")
                    )
                )
            if adjustment.get("cash_received"):
                story.append(
                    p(
                        label("Cash received")
                        + ": "
                        + money(adjustment["cash_received"])
                    )
                )
                story.append(
                    p(label("Change returned") + ": " + money(adjustment["change"]))
                )
            if adjustment.get("reference"):
                story.append(p(adjustment["reference"]))
            story.append(p(adjustment.get("created", "") + " / " + adjustment["actor"]))

            if adjustment.get("replacement_invoice"):
                story.append(
                    p(
                        label("Replacement invoice")
                        + ": "
                        + adjustment["replacement_invoice"]
                    )
                )
    if sale.get("revision"):
        story.append(p(label("Original collection"), "Heading3"))
    cash = sale.get(
        "cash_amount",
        (
            sum(t["amount"] for t in (tenders or []) if t["is_cash"])
            if tenders
            else (
                sale.get("paid_now", sale["total"]) if sale["payment"] == "cash" else 0
            )
        ),
    )
    if cash and "tendered" in sale:
        story += [
            p(label("Cash received") + ": " + money(sale["tendered"])),
            p(
                label("Change returned")
                + ": "
                + money(max(0, sale["tendered"] - cash)),
                "Heading3",
            ),
        ]
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
        p(profile.get("invoice_footer") or label("Thank you for your business.")),
    ]
    if profile.get("return_policy"):
        story += [Spacer(1, 6), p("Return policy: " + profile["return_policy"])]
    if profile.get("exchange_policy"):
        story.append(p("Exchange policy: " + profile["exchange_policy"]))
    import json

    promotion = sale.get("promotion_snapshot") or {}
    if isinstance(promotion, str):
        promotion = json.loads(promotion)
    if promotion.get("code"):
        name = promotion.get("name_ur") if language == "ur" else promotion.get("name")
        story.append(
            p(
                label("Promotion")
                + ": "
                + promotion["code"]
                + " / "
                + (name or promotion.get("name", ""))
            )
        )
    for offer in promotion.get("offers", []):
        name = offer.get("name_ur") if language == "ur" else offer.get("name")
        story.append(
            p(
                offer["code"]
                + " / "
                + (name or offer.get("name", ""))
                + ": -"
                + money(offer["discount"])
            )
        )
    if promotion.get("kind") == "cross_bogo" or sale.get("return_pair_products"):
        story.append(
            p(
                label(
                    "Return all remaining qualifying and reward product quantities together for this cross-product offer."
                )
            )
        )
    for part in tenders or []:
        name = part.get("method_name_ur") if language == "ur" else part["method_name"]
        if part.get("carried_credit"):
            name = label("Return credit") + " / " + (name or part["method_name"])
        story.append(
            p(label(name or part["method_name"]) + ": " + money(part["amount"]))
        )
    if sale["status"] == "returned":
        story.append(
            p(
                label(
                    "Returned items and settlement recorded in adjustment history."
                    if sale.get("revision")
                    else "RETURNED — stock restored. Refund payment must be completed separately."
                )
            )
        )

    def footer(c, d):
        c.saveState()
        c.setFont(FONT_REGULAR, 8)
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
    c.setFont(FONT_BOLD, 10)
    c.drawCentredString(150, 120, product["name"][:45])
    b = code128.Code128(
        value, barHeight=48, barWidth=0.8, humanReadable=True, fontName=FONT_REGULAR
    )
    scale = min(1, 270 / b.width)
    c.saveState()
    c.translate((300 - b.width * scale) / 2, 45)
    c.scale(scale, 1)
    b.drawOn(c, 0, 0)
    c.restoreState()
    c.setFont(FONT_REGULAR, 8)
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
        style.fontName = FONT_REGULAR
    import re
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display

    labels = {
        "Supplier statement": "سپلائر کا کھاتہ",
        "Net payable": "خالص واجب الادا رقم",
        "Increase payable": "واجب الادا رقم میں اضافہ",
        "Decrease payable": "واجب الادا رقم میں کمی",
        "bill": "بل",
        "supplier credit": "سپلائر کریڈٹ",
        "supplier refund": "سپلائر سے واپس وصولی",
        "Current posted entries only; negative balance is supplier credit.": "صرف موجودہ منظور شدہ اندراجات؛ منفی بقایا سپلائر سے قابل وصول رقم ہے۔",
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
                    '<font name="' + FONT_URDU + '">' + escape(x) + "</font>"
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
        text(
            label("Supplier statement" if "supplier" in data else "Customer statement")
            + " / "
            + data.get("supplier", data.get("customer"))["name"]
        ),
        text(
            label("Net payable" if "supplier" in data else "Outstanding")
            + ": "
            + money(data["balance"])
        ),
        *(
            [
                text(
                    label(
                        "Current posted entries only; negative balance is supplier credit."
                    )
                )
            ]
            if "supplier" in data
            else []
        ),
        Spacer(1, 12),
    ]
    table = [
        [
            text(label(x))
            for x in (
                [
                    "Date",
                    "Entry / reference",
                    "Increase payable",
                    "Decrease payable",
                    "Balance",
                ]
                if "supplier" in data
                else ["Date", "Entry / reference", "Debit", "Credit", "Balance"]
            )
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
