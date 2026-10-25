# StockDesk 1.7 — supplier goods returns, credit notes and refunds

This release adds a stock-and-finance return workflow. The full enterprise specification remains incomplete; see CHECKLIST.md.

## Post a supplier return

Open a posted bill in **Supplier payables**, then **Return supplier goods**. Select a reason from the new database-backed supplier-return-reason family, enter the supplier credit-note number/date, explanatory notes and credited tax, then enter quantities from the displayed receipt sources. Search product/batch and page through sources. The UI posts quantities on the current page only; the API accepts up to 100 distinct sources per request.

The server checks receipt provenance against the bill's PO, remaining received quantity, remaining billed quantity, unit precision and actual batch stock. Multiple sources sharing a batch are checked together. Returns may include expired goods. Goods movements, credit lines and audit commit atomically under the tenant lock; an invalid line rolls back the whole return. A successful request replay cannot return stock twice; changed payloads with a used key are rejected. Credit-note numbers are unique per supplier.

Credit value is calculated from the original bill line's amount, not current product cost. Cumulative proportional rounding ensures repeated fractional returns do not create or lose minor units. Credited tax is entered from the supplier's document and bounded by the invoice's remaining tax. It is not statutory tax validation. Zero-value return credits are possible for zero-cost goods or fractional rounding.

**Receipt provenance begins with this upgrade.** Existing receipts lack the required structured source links. Free-text movement notes are not backfilled as proof of supplier/batch origin, so old receipts are not eligible in this workflow. Opening balances and manual stock adjustments are not supplier receipt sources.

## Credit balances and refunds

Bill balance is `original total − posted payments − return credits + posted refunds received`. Positive balances are payable; negative balances are credit owed by the supplier. The register reports positive outstanding and supplier credit separately so credits cannot hide overdue liabilities on unrelated bills.

Unpaid return credits reduce the amount payable. Credits after payment may create an amount owed back by the supplier. Record money actually received using the database payment-method lookup, reference and date. Refunds cannot exceed that credit balance. A refund record can be voided with a reason to correct the ledger; its history remains. This does not reverse a bank transfer or adjust till cash. Enter a separate till movement if physical till cash changes.

Original invoice totals remain immutable. Bills with goods returns cannot be voided. Original receipt quantities remain gross received; a return does not reopen a completed PO or make credited quantities available for billing again. Use a new PO for replacement goods.

## Permissions and limitations

Owner and Manager have the new `supplier_return` capability. Custom roles must explicitly receive it, with stock/finance/cost prerequisites. Existing custom roles are not silently expanded. Refund recording uses finance permission. Stock-only staff cannot post a goods return/financial credit without the combined grant.

Supplier return reasons are separately configurable in Lookup management and seeded with damaged, expiry, wrong-delivery and agreed-overstock reasons, including Urdu labels.

Posted goods returns/credit notes cannot be voided or edited in this release. There is no supplier RMA/authorization portal, replacement exchange, unbilled-goods return, standalone price-only credit, cross-invoice credit allocation, historical provenance repair, independent approval workflow or bank gateway execution. This is not a general ledger. Correct those exceptional cases through an audited operational/accounting process outside this module; do not edit stock/ledger tables directly.

## Upgrade

Back up PostgreSQL, preserve `.env`, replace source and rebuild as described in README. Migrations 001–013 are unchanged. Migration 014 adds structured receipt sources, return credits, refund records and the balance view; 015 adds supplier-return reasons. No historical stock or invoice totals are changed. Default Compose continues to reuse your existing PostgreSQL container/network.

English/Urdu forms, source pagination and mobile layouts are included. Dynamic server errors may remain English. Tests are documented in VERIFICATION.md; real PostgreSQL concurrency, Docker startup and live banking/hardware acceptance remain separate deployment checks.
