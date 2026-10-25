# StockDesk 1.10 — promotions and Excel catalog import

This release completes the bounded features below. It does not complete the full enterprise specification; CHECKLIST.md retains the remaining implementation work.

## Promotions and coupons

Owners and Managers receive the new `promotions` permission. An Owner can grant it explicitly to a custom role. It does not grant sale, cost, settings or user-administration permissions. Cashiers can search active offer codes but cannot create/edit offers or list inactive offers. All reads, product references and writes are tenant-bound. Writes are audited and use the same tenant transaction lock as checkout and price updates.

Open **Promotions and coupons**, choose a code, English/Urdu names and one rule:

- **Percentage coupon:** 0.01%–100% off the invoice subtotal, rounded half up to a minor currency unit.
- **Fixed coupon:** a fixed amount off the invoice subtotal, capped at that subtotal.
- **Buy X get Y free:** one whole-unit SKU. All purchased and free units must be in the cart. For buy 2/get 1, quantities 3 and 6 receive 1 and 2 free units; quantity 2 receives none. The engine does not add products or stock implicitly.
- **Bundle price:** at least two distinct products, with required quantities and one bundle selling price. Only complete bundle sets qualify. Leftover units retain their regular price. Component quantities respect product units; weighted products are supported. A bundle is a pricing rule, not a recipe/BOM inventory assembly.

Optional controls include minimum subtotal, maximum total discount, inclusive start/end dates, a same-day daily time window and a total redemption limit. Date/time calculations use Asia/Karachi. Start time is inclusive; end time is exclusive. End `00:00` means 24:00 at that day's end. Both times blank means all day. Overnight spans and weekday calendars are not supported. A rule that yields no saving is rejected rather than silently accepted.

In POS, select or enter the code in **Promotion / coupon code**. Codes are case-insensitive when applied, stored in uppercase, and cannot be renamed after creation. A sale accepts one promotional rule, or the existing manual discount, never both. Offers are not automatically selected or stacked. The searchable code list includes active rules; the authoritative quote checks cart eligibility, dates and remaining usage. A disabled/expired/exhausted code blocks checkout until removed or replaced.

### Tax, history and retries

BOGO discounts only its qualifying SKU. Bundle savings are allocated proportionally across the matching component amounts. Other products receive no promotional discount. Invoice-wide coupons use the existing largest-remainder allocation. Inclusive/exclusive tax is recalculated from those exact discounted lines. Management reports now read the frozen discount allocations instead of redistributing a product-specific promotion across unrelated products. Manual/legacy invoices retain their existing fallback behavior.

Every promotional checkout must carry the server quote token, including legacy manual-tax businesses. Checkout re-evaluates current rules, prices, time and usage while holding the tenant write lock. Changed rule versions invalidate older quotes. Failed checkouts roll back stock and redemption usage together. Repeating an unchanged successful submission returns its original sale without another redemption, even if the offer was subsequently disabled. Changed submissions under the same request ID are rejected.

Invoice HTML and English/Urdu PDFs display saved code/name details. Offer edits do not rewrite old invoices. Whole-sale returns restore stock using the existing return flow but do **not** restore promotion usage. Limits are global per tenant/promotion, not per customer. Decrease limits only to a number at least the already recorded usage, or disable the offer. There is no hard-delete endpoint.

Held bills retain their code but reserve neither stock nor coupon capacity. Resuming obtains a fresh quote, so an expired/exhausted offer may no longer qualify. Manual discount approval and refund approval workflows remain missing.

## Excel catalog import

**Catalog import → Download Excel template** supplies a single Products worksheet with the same nine columns as CSV. Replace the sample row and use active category/unit lookup codes. Money is entered in major currency units with up to two decimal places; quantities retain up to three decimal places according to the product rules. SKU, category, unit and barcode cells must be text, preserving leading zeros. Existing products are never overwritten.

Upload `.xlsx` (up to 1,000,000 bytes), then **Validate and preview**, review the normalized CSV/rows, and **Import validated products**. Conversion itself creates nothing. The existing preview rollback, tenant lookup checks, atomic commit and idempotent request handling apply to the converted data. A validation failure in any row prevents every row from committing.

Supported workbook shape is one worksheet, exact template headers in row 1, columns A–I, and at most 200 product rows (rows 2–201). Blank rows within that range are ignored. Formulas, error cells, numeric identifiers, date/boolean cells, macros, external workbook links, encrypted files and extra columns/rows are rejected. Expanded ZIP content is capped at 8 MB/200 members, and converted CSV at 200 KB UTF-8. Declared worksheet dimensions are not trusted. This is new-product XLSX import, not `.xls`, multi-sheet mapping, product updates or supplier import.

The frontend proxy allows up to 2 MB only for catalog-import routes to accommodate base64 JSON. Other routes retain the existing request limit. New backend dependencies are `openpyxl==3.1.5` for reading and `defusedxml==0.7.1` for XML parsing; the shipped static template requires no authoring dependency at runtime.

## Upgrade

Back up PostgreSQL and retain `.env`, then rebuild backend and frontend using README. Migration **017_promotions.sql** adds promotion/component/redemption tables and an invoice JSON snapshot. Migrations 001–016 are unchanged. Existing products, stocks, sales, tax settings and default PostgreSQL-container/network configuration are preserved. The new templates directory is included in the backend Docker image through the existing `COPY app` instruction.

See VERIFICATION.md for checks actually executed. Real PostgreSQL concurrency, Docker/proxy startup, physical scanners/printers, live integrations and production deployment are not certified by this release. Offline sync, multi-store inventory, partial returns, loyalty, subscriptions and the other checklist gaps remain implementation work.
