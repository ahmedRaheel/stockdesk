# StockDesk 1.12 — inventory turnover and report exports

## Inventory turnover

Open **Management reports → Inventory turnover** and choose 7, 30 or 90 complete days. API callers may select any 1–90 day period. The report ends yesterday in Asia/Karachi and excludes today's incomplete day. Each SKU shows its unit, opening/closing stock, sold/returned quantities, net sold quantity, average daily closing stock, period turnover and days per turn. The screen shows 100 products per page; exports include every matching product within their bounds.

Opening stock is the movement-ledger balance before the start date. Closing stock is the balance at the end of the last date. Average stock is the arithmetic mean of each day's closing stock, including zero-stock days and days before a newly created product existed. Every stock movement affects this balance; only SALE and customer RETURN movements affect sold/returned units. Returns use their actual movement dates, even when the original sale was in an earlier period. No return is subtracted twice through invoice status.

Period turnover = (sold units - returned units) / average daily closing stock. Days per turn = period days / turnover, only when turnover is positive. Zero average produces an unavailable turnover; non-positive turnover produces unavailable days per turn. Negative turnover is retained when returns exceed sales. Ratios use unrounded decimal quantities and are rounded only for display. This is per-SKU quantity turnover, not annualized turnover or accounting COGS / average inventory cost. Different units are not combined.

The report requires cost permission, includes inactive products with historical stock, reads a consistent tenant-scoped snapshot and caps the result at 10,000 products with an explicit error beyond that limit.

## Excel and PDF exports

Use **Export Excel** or **Export PDF** on product/ABC-XYZ, category, cashier, hourly, tax summary/invoices, current stock age, basket pairs, what-if and turnover reports. Export requests recompute from current authorized data using the applied filters. A later sale, return or catalog change can therefore make a later download differ from an earlier screen. Scenario exports state the applied demand/price/cost assumptions and horizon; stock-age exports state their current as-of date.

Excel stores money as numeric major currency units, quantities/ratios as numbers, identifiers as literal text (including leading zeros), with currency-labelled columns, frozen headers and filters. Formula-like names remain text. Invalid XML control characters are replaced in export text without modifying source records. These are static report snapshots, not connected workbooks or editable forecasting models.

PDF uses landscape A3, repeated table headings, page numbers and the report's methodology notes. Unicode/Urdu business and product text uses bundled fonts and Arabic shaping. Export headings/methodology are English; UI buttons/help support English/Urdu. Full bilingual report labels remain a language gap.

Limits: Excel 10,000 rows; PDF 500 rows. Oversized exports fail explicitly and never silently truncate. Existing source report bounds still apply (10,000 invoices, 50,000 sale lines, 10,000 stock batches); basket analysis retains its documented top-200-pair limit. Use Excel or a shorter period when PDF exceeds its bound. Downloads require the same cost permission as the screen and send no-store cache headers. Nothing is emailed or scheduled.

## Upgrade

Back up PostgreSQL, preserve `.env`, rebuild backend/frontend using README. No new migration or dependency is required beyond 1.11. Migrations 001–017 and the existing PostgreSQL/container network configuration are unchanged.

See VERIFICATION.md for checks and CHECKLIST.md for remaining work. Partial returns/exchanges, offline sync, multi-store inventory, loyalty, subscriptions, scheduled/custom reporting, external integrations and other documented gaps are not completed by this release.
