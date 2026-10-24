# Deployment acceptance

Use a disposable database and fictitious customers. Never test irreversible operations against real inventory.

1. Start Docker Compose from README. Confirm `/api/live`, `/api/health` and `/api/docs` respond.
2. Create two businesses. Create a cashier and stock manager in only the first. Verify each sees its own permissions; verify a hand-edited URL cannot expose the other business.
3. Create two grocery products with whole-unit stock, cost, price and barcode. Test scanner Enter suffix, unknown barcode, repeated scans, and the final remaining unit.
4. Complete a cash sale, re-submit the unchanged request ID, inspect its receipt/PDF, and verify one ledger deduction. Change product name/price and verify the old receipt is unchanged.
5. Submit the same last-unit checkout simultaneously from two clients. Exactly one must commit. Run `RUN_CONCURRENCY=1` tests against real PostgreSQL.
6. Add a supplier. Create a two-line purchase order. Receive part of one line and retry it. Stock increases once. Try receiving more than the remainder: no line may commit. Complete or cancel the remainder and inspect the ledger/audit.
7. Test stock-manager purchasing access and cashier purchasing denial. Test expired/revoked tokens and password-change session revocation.
8. At desktop and tablet widths, inspect dashboard, catalog, POS, purchasing and forecasts. Use keyboard navigation, visible focus, screen reader labels and both density settings. Test touch targets on the actual till display.
9. Test sparse forecast history, zero sellers, out-of-stock items and reported periods. Verify outstanding PO quantities reduce reorder suggestions while stockout estimates still assume no dated replenishment.
10. Disconnect during checkout/receiving. Restore connection and retry the unchanged submission. After a reload, inspect history before creating another order. Offline selling is not supported.
11. Print invoices and Code128 labels on the intended hardware. Validate actual tax, price and currency rules for the deployment.
12. Restore a backup into a separate database. Reconcile products, stock ledger, sales and purchase receipts before accepting the recovery process.

Large-store launch requires the remaining work in ARCHITECTURE.md and measured capacity with realistic catalogs/tills. CI configuration is supplied; its presence does not establish that it has run in your repository.

## Retail 1.2 acceptance

13. Change a lookup label; verify product IDs remain stable. Disable it and verify new products cannot select it. Try a lookup ID from another tenant; the API must reject it.
14. Sell 1.25 kg and verify rounded line totals and exact stock. Try a fraction of a piece unit: reject. Verify cashier responses omit purchase cost.
15. Create a customer, request credit as cashier, approve as owner; reject self-approval. Sell partly on khata and verify the receivable and ledger. Test credit-limit and overdue blocks.
16. Create a monthly plan starting on the 31st; February clamps to month-end and the next month returns to the original anchor. Sum installments equals principal plus markup exactly.
17. Collect a recovery twice with the same request: one ledger/payment effect. Reject changed request payload and excess repayment. Return the original sale: outstanding debt clears once, original batch stock returns, and the refund is handled explicitly outside the app.
18. Receive expired and valid batches. Expired stock cannot be sold; earliest valid batch sells first. A prescription-required product rejects missing references. Batch totals must reconcile to product stock.
19. Hold a cart, resume at current prices and complete it once. A second checkout of that hold under a new request must fail.
20. Open a cashier till, sell cash and recover cash, record a refund cash OUT, reconcile expected/counted cash, and require a note for discrepancies. No-till sales are intentionally outside session totals.
21. Inspect Urdu khata layout and lookup labels on your target device. Full Urdu receipts and full localization are not supplied.
