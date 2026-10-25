# StockDesk 1.14 — invoice returns and exchanges

## Operator workflow

Open **Sales & receipts → Return / exchange** on a fully paid completed invoice. Enter only the quantities physically returned and choose Expired item, Damaged item, Incorrect item, or Opened item. Unsafe goods are written off: a source-batch RETURN and matching OUT leave sellable stock unchanged. Only inspected, unopened incorrect items may be marked Restock. Expired source batches cannot be restocked. For partial quantities from multiple original batches, restocking is rejected until a future batch-selection workflow; record them as non-sellable instead. Full remaining quantities can restore their original allocations.

Optionally add replacement products and quantities. Preview shows return credit, the retained original invoice total, replacement total, and the net amount to collect or refund. Return credit uses the original saved price, allocated discount and tax; replacement products use current prices and configured taxes (or the entered manual rate). Promotions are not re-applied or redeemed by this flow. Prior promotion usage is not restored.

Confirm after physically collecting the net payment or handing over the net refund. Extra cash entered above the amount due produces change. Cash requires the operator's open till; refunds cannot exceed its expected balance. External settlement requires a reference and records that settlement only; it never invokes a bank/card provider. Equal-value exchanges require no cash movement. Settlement can differ from the original tender; automatic refund allocation to original split tenders is not implemented.

The replacement has its own linked invoice and receipt, showing return-credit funding separately from the new collection. The original invoice keeps its number, increments its revision and displays only retained items. Original collection/till entries remain historical; only the net new cash affects the current till. Return history is included on revised screen/PDF receipts. The Original receipt button retrieves the preserved checkout snapshot, with an original-version PDF download.

## Accounting and limits

This is an operational invoice revision/return-credit journal, **not statutory credit-note or general-ledger accounting**. Each adjustment stores the preceding invoice/items, return reasons, stock disposition, credit, linked replacement, settlement reference, actor and result; the initial checkout snapshot is retained separately. There is no adjustment deletion or reversal endpoint. To correct a replacement, use its own return/exchange flow.

Current sales/margin/tax reports use retained quantities and totals at the original sale date, plus replacement invoices at their new date. Thus later returns revise historical sales reports, as existing whole returns already do. They are not return-period tax ledgers. Non-sellable stock movements do not create a general-ledger expense journal. Inventory turnover records return and write-off movements at their actual dates. Rounding is cumulative against original quantities, so repeated fractional returns do not over-refund; the final return credits the remaining exact balance.

Fully paid cash/external/split invoices are supported. Partial khata/receivable adjustments are explicitly blocked; their existing full-return flow remains. A maximum of 100 adjustment events per invoice and 100 returned/replacement lines per request bounds receipt and API work. Batch allocation must exist for the original sale. No gateway, cash drawer, automatic disposal, statutory filing, exchange promotion stacking, independent refund approval or original-tender routing is claimed. The remaining enterprise checklist is still open.

## API and integrity

Prefix: `/api/v1/tenants/{tenant}/sales/{sale_id}/adjustments`.

- POST `/preview`: current revision, selected original item IDs/quantities/reasons/restock flags, optional replacement product IDs/quantities, manual tax rate and prescription reference. Returns exact credit, net and a quote token.
- POST root: preview fields plus quote token, unique request ID, cash/external settlement, tendered cash and reference. Rechecks permissions, revision, stock, pricing and till balance under the tenant write lock; updates invoice, inventory, replacement checkout, till and audit in one transaction.
- GET root: bounded invoice adjustment history (at most 100 events).
- GET `/original`: original invoice/items/tenders with normal sales authorization and cost redaction.
- Existing invoice PDF endpoint accepts `original=true` to print the preserved original.

`return` permission is required; adding replacements also requires `sale`. Duplicate request replay returns the saved result; changed payloads with the same request ID conflict. Stale previews/revisions fail without partial writes. Legacy whole-return commands reject invoices already revised, preventing double stock restoration/refunds. Original checkout retries retain their original response.

## Upgrade

Back up PostgreSQL and preserve `.env`; rebuild backend/frontend as described in README. Migration **019_sale_adjustments.sql** adds revision/journal storage and a dedicated selected-batch return trigger while preserving the legacy allocator. Migrations 001–018 remain unchanged. The default external `postgres` container / `chatbot-network` configuration is preserved. No dependency was added.
