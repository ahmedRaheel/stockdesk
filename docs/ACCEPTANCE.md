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
9. Test sparse forecast history, zero sellers, out-of-stock items and reported periods. Incoming purchase quantities are not yet subtracted from reorder suggestions; the buyer must reconcile them manually.
10. Disconnect during checkout/receiving. Restore connection and retry the unchanged submission. After a reload, inspect history before creating another order. Offline selling is not supported.
11. Print invoices and Code128 labels on the intended hardware. Validate actual tax, price and currency rules for the deployment.
12. Restore a backup into a separate database. Reconcile products, stock ledger, sales and purchase receipts before accepting the recovery process.

Large-store launch requires the remaining work in ARCHITECTURE.md and measured capacity with realistic catalogs/tills. CI configuration is supplied; its presence does not establish that it has run in your repository.
