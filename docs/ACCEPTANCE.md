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

## Release 1.3 acceptance

22. Configure inclusive and exclusive tax profiles, assign a business default and a product override, then sell a mixed cart with a discount. Verify every minor unit reconciles and included tax is not added twice.
23. Expire an assigned profile and verify checkout blocks. Change a rate after obtaining a quote: reject the stale quote. Verify the original invoice remains unchanged.
24. Set disabled mode and verify a client-supplied rate cannot charge tax. Legacy manual mode intentionally retains cashier input; choose configured mode before trading if this is not desired.
25. Collect cash plus bank/wallet, verify split sum and cash change, duplicate the same request once, and check that the till includes only the cash portion. Verify remaining credit still requires customer approval and a due date.
26. Switch English/Urdu on login and within the app, inspect RTL forms and downloaded invoice, and check real Urdu business/product names. Some dynamic messages and customer statements remain English.
27. Add a fractional unit, use it in a product, then attempt to change its quantity rule: reject. Change/deactivate lookup labels without deleting historical IDs.
28. Verify F2 scan focus, F4 validated checkout and F8 hold on the actual POS keyboard. Confirm Alt/Ctrl combinations are not intercepted.


## 1.4 acceptance

1. Configure a keyboard-mode barcode reader to append Enter. Test an actual leading-zero barcode and consecutive reads; compare with manual SKU and quantity entry. Test unknown code and insufficient stock.
2. Count batches as stock staff, submit, then approve as a different manager. Retry posting and confirm exactly one set of adjustments.
3. Open another count, perform any stock movement, and verify posting rejects it; cancel and recount.
4. Check reports against invoices with inclusive/exclusive tax and discount. Verify cashier access is denied.
5. Repeat POS entry in Urdu and at a narrow mobile width.


## 1.5 acceptance

1. Receive part of a PO. Attempt billing more than received, then post an allowed invoice and verify exact PO cost enforcement.
2. Record part-payment from a database payment method. Verify balance and ageing; reject overpayment and cross-tenant records.
3. Void with reasons; payment void restores balance and bill void releases matched quantities without moving stock.
4. Preview CSV and verify no products exist. Submit a file with a bad second row and verify full rollback. Commit a valid file; check barcode zeros and weighted stock. Retry the request and verify no duplicates.
5. Test both English and Urdu screens, mobile widths, actual deployment PostgreSQL and Docker startup.


## 1.6 acceptance

1. As Owner, create a sales-only custom role and assign a Cashier account. Verify costs are absent in product and receipt API responses.
2. Add finance with its cost prerequisite. Verify the already-signed-in user gains the capability on the next request, then loses tenant access when the role is disabled.
3. Attempt an Owner override, a cross-tenant role assignment and delegated team management; each must fail.
4. Restore a built-in role using Team & roles and confirm custom grants are cleared.
5. Give a reviewer read/cost/audit only; search and export the current audit page. Confirm business writes are denied.
6. Check the role editor and assignments in English/Urdu and on mobile. Run real PostgreSQL concurrency/deployment checks before production use.


## 1.7 acceptance

1. Receive and bill goods after upgrading. Return part of a sourced batch with a supplier credit number and lookup reason. Check inventory and payable both decrease once.
2. Retry the identical request; verify no duplicate stock movement or credit. Reject excess source/billed/batch quantity, wrong tenant/source, excessive tax credit and invalid dates.
3. Pay a bill, then return goods. Check a supplier credit balance appears, record a partial external refund, and void only the refund record with a reason.
4. Check three fractional returns sum to the original rounded bill amount.
5. Confirm pre-upgrade receipts are not guessed into return sources; confirm stock-only staff cannot post credits.
6. Test Urdu/mobile return forms and reconciliation using disposable normal PostgreSQL before real inventory.


## Purchasing controls (1.8)

- Owner enables approval at PKR 100; another Manager creates a PKR 400 order. Creator sees pending status without self-approval; receiving is blocked.
- Owner reviews line costs and approves with a reason; receiver can then post the delivery. Rejected orders remain closed. Turning policy off must not release an existing pending order.
- Add two quotes for one product. Change comparison quantity across a minimum and check eligible filtering and price ordering. Verify expired/inactive offers are excluded when filtering and stale updates fail.
- Verify first receipt contributes one performance sample, not one per line, and unreceived orders have no elapsed-delivery value.
- Check Urdu/RTL and mobile layouts. Confirm real PostgreSQL concurrency and deployed Docker health separately before production use.

## 1.9 operational analytics acceptance

- Open Management reports → Operational reports. Compare the tax register against inclusive/exclusive, manual and discounted original receipts. Check that a returned invoice is excluded, and that this is unsuitable as a return-period statutory ledger.
- Compare positive batch quantities to inventory. Verify current cost × quantity rounding and expiry today / expired yesterday. Replenish a batch and confirm its displayed age remains its first creation age.
- Create two shared-product baskets and one single-product basket on a completed reporting day. Check support/confidence/lift. Increase minimum shared baskets to exclude the pair. Export CSV.
- Set demand to +20%, price to -10%, cost to +10%; verify the assumptions and independently calculated projected profit. Verify -100% demand yields zero sales/cost and no margin.
- Confirm Cashier and cross-tenant requests are denied. Switch English/Urdu and inspect reports at mobile width. Download a multi-page Urdu customer statement with mixed Urdu/Latin references.

## 1.10 promotion and Excel acceptance

- Create fixed/percentage coupons, a buy-2/get-1 offer, and a two-product bundle with a weighted component. Verify leftover units, quantity requirements, caps, minimum spend and no-discount rejection.
- Check daily start/end boundaries in Asia/Karachi, inclusive end dates, inactive rules and exhausted caps. Verify Cashier cannot edit and another tenant cannot select the component products.
- Hold/resume a promotional bill. Change/disable the rule before checkout and require a refreshed/eligible quote. Confirm old receipt code/name/discount remain unchanged after editing the offer.
- Complete the last permitted redemption from two clients against real PostgreSQL. Exactly one new sale may commit; repeat its unchanged request ID and confirm no second deduction/redemption. PGlite checks do not replace this concurrency acceptance.
- Check product-specific discounts with mixed inclusive/exclusive taxes and compare product profit reports. Return an invoice and confirm usage remains consumed.
- Download Excel template, replace the sample row, preserve barcode leading zeros as text, and preview/commit. Test one invalid row and confirm no products are added. Reject formulas, numeric barcodes, extra columns and oversized content. Confirm deployment proxy accepts valid uploads larger than its former 100 KB limit.
- Inspect English/Urdu POS, promotion administration, receipt PDFs, Excel preview and mobile layout with realistic product names.

## 1.11 cash and supplier statement acceptance

- Bill 1,250.50 / cash 2,000.00: POS, receipt and PDF must show change 749.50; till increases only 1,250.50.
- Split 500 external + 750.50 cash applied / 1,000 cash handed over: return 249.50. Khata uses cash paid now, not full invoice total. Exact cash returns zero; short cash blocks checkout.
- Reopen receipt and retry the original checkout: same cash/change and no duplicate sale.
- Supplier statement balances must match posted bills less payments/credits plus refunds; voided transactions excluded. Confirm English/Urdu rendering, tenant isolation and finance-only access.

## 1.12 turnover and report export acceptance

- Verify opening/closing balances against the movement ledger for the selected Karachi dates. Include a no-movement day, a new product, weighted quantity, zero stock and a return from an earlier sale.
- Return posted today must not alter yesterday's turnover; a return inside the window reduces net sold units and changes stock only from its actual date.
- Export product/category/cashier/hour, tax, stock, basket, scenario and turnover data to Excel/PDF; compare dates, applied scenario assumptions and values. Excel money is major currency units, and SKUs/formula-like names remain text.
- Deny cashier/cross-tenant export requests. Refuse oversized exports without truncation. Confirm 100-row UI pagination does not limit exported records.
- Report PDFs are landscape A3; confirm fit-to-paper on the actual printer before operational use. Downloaded values are regenerated from current data, not a frozen browser snapshot.

## 1.13 alert-center acceptance

- With ALERT_WORKER_ENABLED=true, create a low-stock rule and wait for automatic evaluation. Repeat evaluation without duplicate live events. Verify the existing batch alert dashboard still works.
- Acknowledge with a note; replenishment must resolve the same episode. Reduce stock again and confirm a new unacknowledged episode appears.
- Test expiry today, already expired, boundary day and one day outside the window; ignore zero-stock and undated batches. Check weighted thresholds and per-product scope.
- Edit/disable a rule: existing episodes close with rule_changed. Reject stale versions, cross-tenant products/events and Cashier writes. Confirm audit entries.
- Under real PostgreSQL and two application workers, race evaluation with stock changes and acknowledge/disable actions; assert one live episode per rule/entity. Test graceful shutdown and inspect errors/stale evaluation timestamps. This production acceptance is not established by single-process PGlite checks.


## 1.14 invoice adjustment acceptance

Exercise an expired/damaged/opened return (no sellable stock increase), an inspected incorrect-item restock, partial/repeated returns, a more expensive exchange with extra cash/change, a cheaper exchange/refund, and an equal-value exchange. Check original/revised/replacement receipts, PDF, net till movements, failed replacement rollback, stale revision and duplicate request protection. Verify current historical reports revise retained sales values, while movement dates remain current. Reject insufficient till cash, short tender, unsafe/expired restock, excessive quantity, missing external reference and unauthorized/cross-tenant requests. Partial khata, gateways and statutory credit-note acceptance remain out of scope.


## 1.15 acceptance

Export a filtered editable workbook; retain leading-zero barcodes and literal text. Re-upload in update mode, review old/new values and apply. Check whole-file rollback, duplicate/missing SKU rejection, unit/opening-stock guards, stale preview protection, stock/metadata preservation, retry deduplication, role/tenant boundaries and 200-row export limits. Configure Sunday 22:00–02:00; verify Sunday 22:00 and Monday 01:59 qualify while Monday 02:00 and Sunday 01:00 do not. Verify effective end dates anchor to the start day. Check migrated promotions still select all days.


## 1.16 cross-product BOGO

Create buy-2-Tea/get-1-Milk, then edit and verify product roles persist. Add two Tea and two Milk to POS: only one Milk is discounted. Complete cash payment and verify change and receipt/PDF policy. Reject a partial promotional-product return; select all promotional items and complete the net cash refund. Return unrelated lines independently, edit the live promotion, and verify original policy and credits remain unchanged. Repeat with native randomUUID unavailable; check Urdu/mobile rendering.


## 1.17 per-customer promotion limits

Create an offer with per-customer cap 1 and verify it persists after editing. Applying its code without a registered customer must fail. Complete a sale for customer A: subsequent uses, including stale quotes, must fail; B remains eligible. Retry the first request and verify no second redemption. Return the invoice and verify A remains exhausted. Failed checkout must not consume usage; global caps still apply. Sales-only staff can select customers without viewing credit data. Check Urdu/mobile and HTTP UUID fallback.


## 1.18 automatic promotions

Mark two offers automatic; verify edit retains the flag. Enable automatic selection in POS and verify the lowest final tax-inclusive total wins. Hold/resume preserves the choice. Complete checkout and inspect the selected offer on the receipt. Exhaust the winner and verify the next eligible offer wins. A stale quote must fail; retrying the successful request must not consume another redemption. Check exact-total ties, no eligible offers, schedules, minimums, registered-customer limits, mixed taxes, Urdu/mobile and HTTP UUID fallback.


## 1.19 alert escalation

Create a warning/info low-stock rule with a one-minute escalation threshold and verify edit persistence. Open an alert, leave it unacknowledged, and evaluate after the deadline: it becomes critical once. Filter escalated alerts, acknowledge it, replenish stock and evaluate again: resolution retains escalation history. Acknowledging before the deadline or clearing stock before evaluation must prevent escalation. Verify recurrence starts a new timer, critical rules reject escalation configuration, and Urdu/mobile displays the history.


## 1.20 quiet hours and customer feedback

Configure all-day quiet hours and verify a low-stock match does not open an alert; clear quiet hours and evaluate to open it. Existing acknowledged/cleared episodes must continue to behave correctly. Test overnight boundaries and deferred escalation. Record rated feedback with an optional invoice, retry it without duplication, resolve and reopen with notes, reject stale versions and foreign invoices, and confirm unauthorized roles cannot read or mutate feedback. Check Urdu/mobile and HTTP UUID fallback.

## 1.21 transaction controls

- Enable both approval policies as Owner; another Manager approves a discounted POS order. Verify self-approval, changed data, revoked approver and expired requests fail; unchanged checkout retries create one sale.
- Sell from two batches, explicitly return the later batch, then return the earlier batch. Verify lot stock and remaining sold quantities; reject unknown, duplicate, expired-restock and excessive quantities.
- Make an installment khata sale with markup, record a recovery, partially return an item and inspect separate paid/credited schedule values. A recovery after preview must invalidate confirmation. Fully return remaining goods and reconcile debt, explicit waiver if any, refund and till movement.
- Request approval for a partial return; approve from a separate user and confirm. Verify legacy full-return API also requires approval when enabled.
