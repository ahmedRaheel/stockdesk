# StockDesk 1.3 — bilingual operations, configurable taxes and split payments

This release extends 1.2. It does not complete the enterprise specification. Existing stock, khata, batches, purchasing and forecasting functionality remains. See the full outstanding scope in RELEASE-1.2.md; changes below supersede its tax, split-payment and localization limitations.

## Tax rules and when tax applies

Open **Tax configuration** as Owner/platform administrator. Staff without settings permission cannot change configuration.

- **Disabled:** no tax is charged, regardless of a cashier-supplied rate.
- **Configured:** the business default applies unless the product has an assigned profile. A zero-rate profile explicitly exempts a product. No default and no product override means zero tax.
- **Legacy manual:** preserves previous installations' behavior; the cashier supplies the invoice rate. Move to configured mode to prevent manual-rate selection. Upgraded and new businesses initially retain manual mode for compatibility.

Profiles contain English/Urdu names, rate in basis points, inclusive/exclusive pricing, active flag, and optional inclusive start/end dates interpreted in Asia/Karachi. An assigned inactive/future/expired profile blocks checkout instead of silently falling back to zero. Dates do not automatically select another profile: the owner must change the assignment. No statutory rate or legal applicability is assumed.

Mixed tax profiles are supported in one bill. The fixed invoice discount is allocated across lines proportionally using largest remainders, preserving every minor unit. Each line's tax rounds half up. Inclusive tax is extracted; exclusive tax is added. Total is subtotal minus discount plus tax minus included tax. An authoritative server quote is displayed before checkout; configured/disabled modes require a matching quote token. Changed prices/rules require another quote. The token is a consistency fingerprint, not an authorization credential; the server always recalculates.

Invoices retain the complete tax snapshot and included-tax amount. Profile edits do not rewrite old receipts. This is a single percentage per line, not compound taxes, geographic tax discovery, withholding, FBR submission or fiscal certification.

## Split payments

Enable **Split payment**, add up to ten payment parts, select active payment-method IDs from the database, enter applied amounts and optional external references. Parts must total `paid_now`. Any remaining invoice balance requires a selected approved khata customer and due date. Cash received must cover the cash part, not the entire invoice. Change equals tendered cash minus applied cash.

Tender method names and cash classification are snapshotted on the invoice. Receipts list each tender. Till totals count the stored cash amount only. Wallet, bank and card entries record payments collected elsewhere: no gateway charge or settlement verification occurs. Whole returns still require an explicit external refund and cash OUT when appropriate. Partial returns, exchanges and refund allocation across tenders are not implemented.

## English and Urdu

A shared locale store controls login and the application. The language choice persists in the browser. Urdu switches page direction, navigation, form labels, table headings, operational instructions and invoice printing. Lookup records keep stable IDs and can have separate Urdu display names. No product/customer name or submitted enum is translated into another stored value.

Noto Naskh Arabic regular/bold is bundled locally for Urdu glyph coverage; there is no third-party font request at runtime. The OFL license is included. Invoice PDFs accept `language=en|ur`; Urdu text uses shaping/bidi handling and embedded fonts. Numeric values retain western digits and the tenant currency code, with Latin identifiers preserved. The khata module uses Rs. formatting for PKR.

This is not a claim of exhaustive localization: some dynamic API validation/error messages, CSV exports, Plotly-generated labels, and customer-statement PDFs remain English. Product/customer data is entered by the business. Urdu search aliases are matched literally; there is no automatic Roman Urdu transliteration. Customer-statement PDF shaping is still pending. `npm run check:locales` checks literal UI labels passed to the translation helpers; it does not prove whole-app translation coverage.

## Reference data and keyboard operations

The implemented lookup families are categories, units, payment methods, adjustment reasons, return reasons and customer segments. Tax profiles have their own typed database resource. Return forms now include the return-reason lookup. New units can enable fractional quantities; that quantity rule cannot change after a product uses the unit. Existing lookup IDs remain stable when labels change or records are disabled. Customer segments are reference records only; segmentation rules/campaigns are not implemented.

F2 focuses barcode/SKU entry, F4 activates the enabled checkout button, and F8 activates the enabled hold-bill button. Shortcuts apply only on POS with no dialog open and do not intercept Alt/Ctrl/Meta combinations. Keyboard-wedge barcode/QR readers work when their payload matches a product barcode/SKU; camera decoding and vendor SDK integration are not included.

## Upgrade and verification

Back up the existing database. Preserve `.env`; replace source and rebuild the backend/frontend. Default Compose continues to reuse `postgres` on external `chatbot-network`. Migrations 001–007 are unchanged; 008 adds tax profiles/snapshots and 009 adds tender records/cash allocation. Existing sales' cash amounts are backfilled; historical tender parts cannot be reconstructed and are left empty. Existing invoices remain valid.

Inspect history before resubmitting a checkout that was uncertain during the upgrade. Client payload signatures gained quote/tender fields; an old request reused with a different payload is rejected rather than duplicated.

See VERIFICATION.md for executed checks. Docker/normal PostgreSQL multi-process tests and actual printer/scanner hardware acceptance still need to run in the deployment environment.

## Still outstanding from the requested complete system

- Multiple locations/warehouses, transfers, franchise/region hierarchy, store-level prices/taxes and scoped access.
- Custom roles, supervisor PIN/biometric, general approval limits/workflows, support consent/impersonation and broader actor portals.
- Offline committed sales, device identity, safe conflict resolution and reliable synchronization.
- Partial returns/exchanges, promotion engine, coupons, BOGO, bundles, happy-hour pricing and currency conversion.
- Product variants/serials, inventory counts, BOM/recipes, pack conversion, landed cost and FIFO/LIFO/weighted-average valuation.
- Supplier returns, price comparison, three-way matching, payables, supplier portal and automatic PO delivery.
- Loyalty, points, wallets/gift-card liabilities, memberships, campaigns and customer-feedback workflows.
- Weather/festival-adjusted models, pricing optimization, churn, cash-flow probabilities, supplier delay, shrinkage, basket analysis, staffing and what-if models.
- Configurable push/email/SMS/WhatsApp/voice delivery, quiet hours, escalation and background-job operations.
- ABC/XYZ, complete profit/tax reports, X/Z reports, report builder/scheduling, Excel import/export and consolidated financials.
- Subscription plans/metering/billing, native apps, white-label, automated backup/restore, SSO/MFA and measured uptime.
- Payment, accounting, marketplace, delivery, e-invoicing, scale/printer/drawer/RFID integrations and webhooks.

These are unimplemented modules, not merely credential switches. Do not advertise them as shipped. GDPR/PCI-DSS compliance and 99.9% uptime are not certified by this source package.
