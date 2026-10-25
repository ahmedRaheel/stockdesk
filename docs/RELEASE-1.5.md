# StockDesk 1.5 — supplier payables and CSV onboarding

This release adds working modules to 1.4; the complete enterprise specification is not yet implemented. See CHECKLIST.md for the consolidated status.

## Supplier invoices and payments

Open **Supplier payables** as Owner or Manager. Stock Manager and Cashier cannot access the finance API or screen. Search purchase references/suppliers, select an order from the database, enter the supplier invoice number/dates/tax and quantities, then post.

Matching checks the purchase order, cumulative received quantity and previously posted supplier bills. Only received, unbilled quantities can be invoiced. Unit costs must equal the agreed PO cost; there is no tolerance or override workflow. Zero quantity excludes a UI line. Fractional quantities obey the product unit. Line amounts round half up to currency minor units. This is cumulative PO/receipt/invoice matching, not individual delivery-note allocation or OCR matching. Cost disputes must be resolved outside this module; posted PO costs are not editable here.

Invoice numbers are unique per supplier, including voided documents. Bill and payment request identifiers protect retries; changing data under a used key returns conflict. All writes hold the tenant lock used by purchasing. Posting bills never changes product cost or inventory.

Select payment methods from the active database lookup. Record partial or full external payments with a reference and date. Overpayment and future payments are blocked. History preserves the method label, actor and amount. Outstanding balances and ageing (not overdue, 1–7, 8–30, 31+ days) are calculated as of today in Asia/Karachi. These are present balances, not historical as-of accounting statements.

Corrections use reasoned voids; nothing is deleted. Void active payments before voiding a bill. A voided bill releases its quantities for a corrected invoice with a new number. Payment voids reverse the ledger record only: they do not reverse bank transfers or issue refunds. Recording cash payments does not automatically reduce till cash; a separate cash OUT is needed if cash physically leaves a till.

Limitations: no supplier credit notes/returns, advances, multi-invoice payment allocation, withholding, exchange gains/losses, general ledger, independent finance approval, tax validation or bank reconciliation. Supplier tax is entered from the document; there is no statutory calculation or FBR integration. Existing historic receipts are not turned into guessed liabilities automatically.

## CSV catalog import

Open **Catalog import**. Download the UTF-8 CSV template. Use the exact columns:

`sku,name,category_code,unit_code,barcode,price,cost,initial,reorder`

Category/unit codes must exist and be active in Lookup management. Amounts are major currency (e.g. `150.50` PKR), with at most two decimal places. Keep barcode cells as text in spreadsheet editors; zeros already lost in Excel cannot be recovered. Maximum 200 products and 200 KB per UI file.

Validate and preview runs the same product creation rules inside a rolled-back transaction. It creates no products, stock movements or audit entries. Commit repeats validation under the tenant lock and creates all rows in one transaction. An invalid later row rolls back earlier rows. Repeated successful request IDs return the same product IDs; a new request cannot silently update existing SKUs/barcodes. Preview does not reserve identifiers.

This imports new basic products only. Existing product updates, XLSX parsing, expiry-required flags/dated opening lots, tax-profile assignment, supplier/customer imports and an onboarding wizard remain outside this importer. Set additional product fields through the existing catalog before selling. Do not use basic opening balances for expiry-tracked medicines.

## Upgrade

Back up the database and preserve `.env`. Rebuild backend/frontend using README instructions. Default Compose still uses your existing PostgreSQL on `chatbot-network`. Migrations 001–010 are unchanged; 011 creates the supplier ledger, and 012 adds import deduplication records. No data is removed and no extra PostgreSQL image is added.

API contracts are in docs/openapi.json. New screens include English/Urdu labels and RTL. Dynamic API errors and some exports remain English. No live provider transfers, notifications, legal compliance or uptime guarantees are represented by this release.
