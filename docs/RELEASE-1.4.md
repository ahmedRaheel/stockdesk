# StockDesk 1.4 — POS entry, stock counts and management reports

This is an incremental working release, not completion of the full enterprise checklist.

## Barcode reader and manual entry

At Point of sale choose **Barcode reader** or **Manual entry**. USB/Bluetooth readers must operate as keyboard input and send Enter after the code. F2 focuses the code field. Codes retain leading zeros; matching is against an active product's exact barcode or SKU. Enter submits one read; another read increments the same cart line. Set Entry quantity for weighted quantities. In manual mode type a code and click Add to bill, or search the separate catalog and select a product. Unknown codes and quantities exceeding stock leave the cart unchanged. The server remains authoritative for unit, available stock, expiry, price and tax validation at checkout.

The mode persists in that browser. There is no camera decoder, device SDK, scale integration, or offline committed checkout. Physical hardware acceptance is still required.

## Stock counts

Stock staff open a reference and select up to 200 products (maximum 500 existing batches). All batches, including zero balances, are captured. Enter physical quantities per batch, save, then submit. A different Owner or Manager reviews and posts adjustments with a note. The creator cannot approve their own count, including an Owner. A posted count cannot be edited or cancelled; correction requires another controlled count.

Any intervening stock movement invalidates posting, even when movements net to zero. Cancel the stale count and start again. Posting validates every revision before writing any movement, then commits movements, status and audit together. Repeating a successful post does not duplicate adjustments. Quantities must obey the product unit. Counts cover the current single inventory location; multi-warehouse counting and importing new unknown lots are not implemented. Expected balances are available through the authorized API; this is not a security-enforced blind count.

## Management reports

Owner, Manager and other roles with cost permission can view 7/30/90 complete days ending yesterday in Asia/Karachi. Cashiers cannot access this API. Reports include net sales excluding tax, recorded sales cost, gross profit, product/category/cashier/hour breakdowns, and ABC/XYZ with CSV export.

Invoice discounts use exact minor-unit allocation. Included tax comes from the frozen invoice snapshot. Cost uses recorded sale-line costs, not landed cost or a new valuation engine. Returned invoices are excluded as whole invoices; this is not a dated refund accounting ledger. Category classification uses the current catalog category. Product ABC ranks positive net sales using cumulative 80%/95% bands. XYZ measures daily unit-demand coefficient of variation: X <= 0.5, Y <= 1, otherwise Z. Fewer than 14 complete observed days show insufficient history; zero sales show no sales. These are descriptive analyses, not AI forecasts.

API windows are 1–90 days, capped at 10,000 invoices and 50,000 lines per request. Shorten the range if exceeded. Large catalog tables are not virtualized. This is not a complete accounting, statutory tax, X/Z or consolidated financial report system.

## Upgrade

Back up the database and preserve your `.env`. Replace application source and rebuild using the README commands. Migrations 001–009 are unchanged; 010 adds stock count tables and movement revision tracking. No second PostgreSQL image is required. Existing tax, split-payment, Urdu/RTL, khata and installment behavior remains. Keep another Owner/Manager account available for independent count approval.

## Enterprise checklist status

The outstanding list in RELEASE-1.3.md remains authoritative except that single-location batch counts, descriptive ABC/XYZ, and basic management profit breakdowns are now implemented as described above. In particular, offline synchronization, multi-store/warehouse transfers, custom scoped permissions, partial returns/exchanges, promotions, supplier returns/payables, loyalty, advanced prediction models, automated external notifications, subscription billing, native apps, SSO/MFA and external integrations remain unimplemented. Provider credentials alone do not enable those modules. No uptime or compliance certification is claimed.
