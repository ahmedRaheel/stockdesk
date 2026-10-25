# StockDesk 1.11 — cash change and supplier statements

## Cash received and change

Enter the customer's actual cash in **Cash received**, even when it exceeds the amount due. POS displays **Change to return** immediately. **Exact cash** fills the currently quoted cash amount. An insufficient amount displays the remaining cash required and blocks checkout. Checkout still validates against the authoritative server total.

Example: bill PKR 1,250.50, cash received PKR 2,000.00, change returned PKR 749.50. Printed HTML receipts and English/Urdu PDF invoices now show cash received and change returned. Reopening the sale retains these values; retrying a checkout returns the same cash/change values without another sale.

For split payments, subtract only the cash portion from cash received. A PKR 1,250.50 bill with PKR 500 paid externally and PKR 1,000 cash received returns PKR 249.50. For khata, cash change is calculated from the cash paid now, not the full invoice or outstanding credit. Revenue, payment allocations and till totals retain only net cash applied to the bill. Change is not a sale refund, credit balance or extra payment. External-only payments show no cash-change section.

## Supplier statement PDF

Open **Supplier payables**, then **Supplier statement PDF** beside a supplier's bill. It includes all that supplier's currently posted bills, payments, goods-return credits and recorded refunds, ordered by document date and posting time with a running balance. Positive amounts increase net payable; negative amounts decrease it. A negative closing balance means money owed by the supplier. Voided bills/payments/refunds are excluded. A statement describes the current ledger state, not historical as-of accounting or a general ledger.

English/Urdu follows the selected UI language. The API requires finance permission, binds supplier lookup and every ledger query to the tenant, and uses a consistent database snapshot. It refuses statements exceeding 5,000 entries rather than truncating balances. The JSON endpoint exposes the same calculation for headless consumers. No email or WhatsApp message is sent.

## Upgrade and limits

Back up PostgreSQL and retain your `.env`, then rebuild backend/frontend using README. No new migration or dependency is required beyond 1.10 (migrations through 017 remain unchanged). The existing PostgreSQL/container network configuration is preserved.

See VERIFICATION.md for executed checks and CHECKLIST.md for outstanding work. Offline sync, multi-store operations, partial returns/exchanges, loyalty, subscriptions, external integrations and other listed items remain implementation work; this release does not claim full checklist completion.
