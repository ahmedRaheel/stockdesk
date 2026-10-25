# StockDesk 1.15 — catalog updates and promotion schedules

## Bulk update existing products

Open **Catalog import → Update existing products by SKU**. Use **Export editable Excel** to download current data, optionally filtered by a literal name/SKU/barcode search. Export includes active and inactive matches; it rejects more than 200 matches instead of silently truncating them. Edit and upload that XLSX file, or use the same exact nine-column CSV format as the existing template.

The update key is the existing tenant SKU (case normalized to uppercase). Update mode never creates a missing SKU or renames one. Duplicate SKUs, barcode collisions, unknown/inactive reference codes and invalid rows reject the whole file. Supported changes: name, barcode, category, price, cost and reorder level. Blank barcode explicitly removes it. Price, cost and reorder must be supplied; use numeric zero explicitly when intended. Money in files and previews is in major currency units with at most two decimals. Opening stock must be zero. Units cannot change; stock, stock revisions, active status, tax profile, expiry tracking, generic/strength/prescription fields and search aliases are preserved. Existing catalog validation still applies, including active tax-profile checks.

**Validate and preview** shows changed fields with before/after values, or No changes. Preview performs and rolls back the same writes and validations as commit, leaving no product/movement/audit changes. **Apply reviewed updates** rechecks the reviewed product/reference state under the tenant write lock. If catalog metadata changed after preview, the whole update rolls back and requires another review. Stock movements alone do not invalidate a preview and are never overwritten. Retries using the same request ID and file/mode return the saved outcome without applying a second update; changed content/mode conflicts.

All rows succeed together. There is no mixed create/update upsert mode, automatic SKU creation, stock import, unit conversion, deletion or silent skipping. Files remain limited to 200 rows, CSV 200 KB or XLSX 1 MB with the existing zip/XML/formula/macros/external-link checks. Export writes identifiers and text as literal Excel strings to preserve leading zeros and prevent formula execution. Unsupported spreadsheet control characters fail explicitly. Barcode swaps between existing products in one file can fail uniqueness checks; use explicit separate reviewed edits instead.

Import/export requires product permission; update and cost-bearing export additionally require cost permission. A summary audit records the updated fields (cost changes are flagged without storing numeric costs in that summary). Existing product-update audits remain. Processed count includes unchanged rows. This completes the bounded update-import checklist item, not variants, serial tracking, recipes/BOM or legacy XLS support.

## Weekday and overnight promotions

Promotion forms now offer Monday–Sunday checkboxes. Select at least one day. All seven are selected by default, including on migrated promotions. One daily window applies to the selected days; leave both times blank for all day. Times use Asia/Karachi. A start earlier than end is same-day; end earlier than start means the window continues after midnight. Start is inclusive and end exclusive. UI end 00:00 still means 24:00 at the end of the start day.

Weekdays and effective start/end dates refer to the **window's starting day**. For example, Sunday 22:00–02:00 with an end date on that Sunday includes Monday 01:59 and excludes Monday 02:00. Early Sunday 01:00 belongs to Saturday's window and does not qualify for a Sunday-only offer. Invalid/equal endpoints, half-specified windows, duplicate/empty/out-of-range weekdays are rejected. Checkout rechecks eligibility, rule version and usage just as before. Automatic offers, stacking, cross-product BOGO and per-customer limits remain missing.

API promotion create/update adds `weekdays`, a list of distinct integers 0 (Monday) through 6 (Sunday). Existing clients omitting it default to all days; deploy frontend and backend together. Existing date and minute fields retain their names. The end minute remains 1–1440; start remains 0–1439.

## API and upgrade

Catalog prefix: `/api/v1/tenants/{tenant}/catalog-imports`.

- POST `/preview`: `csv_text`, optional `mode` (`create` default, or `update`). Update results include `changes` and `preview_token`.
- POST root: the same fields plus `request`; update requires the current `preview_token`. Create-mode request signatures remain backward compatible.
- GET `/export.xlsx?q=...`: editable current-product workbook, at most 200 matches, no-store response.
- Existing `/convert-xlsx` and template downloads remain unchanged.

Back up PostgreSQL and preserve `.env`, then rebuild backend and frontend. Migration **020_promotion_schedules.sql** adds weekday defaults and replaces only the old daily-window constraint; migrations 001–019 remain unchanged. Update imports reuse the existing import journal and need no new table. No dependency was added. The default existing `postgres` container / `chatbot-network` setup is preserved. See CHECKLIST.md for the substantial remaining enterprise work; this release does not claim full completion.
