# StockDesk 1.9 — operational analytics and Urdu statements

This release completes the bounded additions below. It does not complete the enterprise specification. The remaining work is recorded in CHECKLIST.md.

## Open the reports

Choose **Management reports → Operational reports**. The API requires the existing `cost` permission, so Cashiers and unauthorized tenant users cannot retrieve these data. Select a report, set filters, then **Apply filters**. All reports offer CSV export; monetary CSV columns contain integer minor units. Spreadsheet formula prefixes are escaped. Labels support English/Urdu and RTL; CSV column names remain English.

### Tax register

Lists original, frozen invoice tax amounts and groups them by saved profile/name, basis-point rate and inclusive/exclusive treatment. The 7/30/90-day window contains complete Asia/Karachi business days, ending yesterday. Included tax is extracted from net sales; it is not added again. Manual/legacy invoices are identified separately. Inconsistent frozen snapshots fail explicitly instead of producing misleading totals.

Only currently completed invoices are included. A later whole-sale return excludes the original invoice from its original reporting window. This is an operational reconciliation report, not a statutory filing, fiscal X/Z report, immutable period ledger or date-of-return adjustment register. Filing-grade return accounting remains missing.

### Stock age and valuation

Displays every positive batch, its unit, lot, expiry, age band (0–30, 31–60, 61–90, 91+ days), expiry status and value. Valuation uses **current catalog cost × remaining quantity**, rounded half up per batch to a minor unit. Expired and next-30-day expiry value totals are separated. Expiry today remains eligible under the existing sales rule.

This is the current stock snapshot, independent of the sales date filter. Age starts at first batch creation; later replenishment of the same batch does not reset it. Migrated batch age starts at migration. There are no historical receipt-cost layers, FIFO/LIFO costing or inventory-turnover denominator claims. Quantities in different units are never summed into one total.

### Basket analysis

Counts distinct product co-occurrence per currently completed invoice. Repeated quantities do not inflate counts. Support = shared baskets / all invoices; A→B confidence = shared baskets / baskets containing A; lift = shared baskets × all invoices / (A baskets × B baskets). The minimum shared-basket count is configurable (at least two). Up to 200 qualifying pairs are shown, ranked by shared baskets then lift. Both confidence directions, SKU and product names are included in CSV.

This is descriptive association, not causation, personalized recommendations or evidence a discount will increase profit. An invoice with more than 100 distinct products is rejected by this report to bound pair generation.

### What-if simulation

Projects average daily net sales and frozen sale-line cost over 1–365 days. Separate integer changes of -100% to +500% apply to demand, price and unit cost. Demand scales both revenue and cost; price changes affect revenue only; unit-cost changes affect cost only. Baseline and scenario profit are shown with exact half-up rounding. Zero revenue has no defined margin percentage.

The inputs are assumptions, not a trained forecast or price-elasticity model. Tax, overhead, inventory constraints, promotions and seasonality are excluded. No prices, inventory or purchase orders are changed.

## Urdu customer statement PDFs

The Khata statement download now passes the selected interface language. `/customers/{id}/statement.pdf?language=ur` uses bundled Urdu fonts, Arabic shaping, bidi ordering and reversed table columns. English remains the default; invalid language values are rejected. Names and references are escaped. Sale, recovery, return and markup labels are translated; arbitrary user-entered references retain their original language. Table headings repeat over multiple pages.

## Limits, upgrade and validation

The report rejects more than 10,000 invoices, 50,000 sale lines or 10,000 positive batches instead of silently truncating. Invoice date filters do not filter current stock. This version introduces **no database migrations** and preserves migrations 001–016 byte-for-byte. Back up PostgreSQL, retain `.env`, and rebuild using the existing README instructions. The existing PostgreSQL container/network configuration is unchanged.

See VERIFICATION.md for executed checks. External integrations, offline sales, multi-store operations, promotions, native apps, and the other checklist gaps remain implementation work.
