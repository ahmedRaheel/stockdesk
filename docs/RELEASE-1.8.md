# StockDesk 1.8 — purchasing controls and supplier comparisons

This release implements another part of the enterprise checklist, not the entire specification. See CHECKLIST.md for remaining work.

## Independent purchase approval

In **Purchasing → Purchase approval policy**, an Owner can enable approval and set a threshold in the business currency. The default is disabled, preserving the existing workflow. A zero threshold applies to all new orders. The threshold comparison is inclusive and uses the sum of each PO line's quantity × unit cost, rounded half-up to a minor currency unit. It excludes tax and freight because those are not PO fields.

At creation, the server freezes the policy decision, threshold, order total and supplier lead time. Qualifying orders start as `pending_approval`. Their creator cannot approve or reject them, even if the creator is an Owner. A different authorized user opens **Review order**, reads quantities and costs, then records approval or rejection with a required reason. Approval opens receiving; rejection closes the order. Decisions are immutable and matching retries are idempotent. Pending/rejected orders cannot receive stock or count as incoming stock in the existing forecast calculation.

Owner and Manager receive `purchase_approve`; custom roles must explicitly receive it with stock/cost prerequisites. Configure another approver before enabling the policy. Policy changes do not release existing pending orders. This is a single-step approval rule, not budget control, per-user spend limits, multi-stage approvals or supplier authorization. Stock operators can cancel an unreceived remainder, including a pending order; cancellation does not send a supplier message.

## Supplier quotes

**Purchasing → Supplier insights** maintains one current quote per supplier/product. Search dropdowns query the database, 50 matches at a time; narrow by supplier or product name/SKU. Enter price per catalog unit, minimum quantity, quoted lead time, validity dates and notes. Editing requires the current version; stale edits are rejected. Supplier/product identities cannot be changed on an existing quote. Disable an obsolete quote instead of deleting its audit history.

Compare a single product for a requested quantity. The eligible-only filter requires an active offer/product, current validity dates and a quantity at least the quoted minimum. Dates use Asia/Karachi. Quotes sort by product SKU, then unit cost, lead time and supplier. Comparison prices exclude tax, freight, currency conversion and pack conversions. Quotes are advisory: they do not automatically change PO prices, supplier lead-time defaults, catalog costs or invoice matching. This is not tiered pricing, historical quote revision browsing or an EDI supplier portal.

## Delivery performance

The report shows orders, completed orders, orders awaiting approval, open orders, late open orders, first-receipt sample count and average elapsed days to first receipt. Approval date starts the clock for approved orders; otherwise creation date does. Late counts use the supplier lead time frozen when the order was created. Legacy orders have no lead-time snapshot and are excluded from late counts. A first partial receipt counts as the first delivery; the metric does not measure full-delivery time, quality or prediction confidence. Completed status remains based on gross receiving, even after supplier goods returns.

## Upgrade and limits

Back up PostgreSQL and preserve `.env`, then follow README's rebuild steps. Migration 016 extends purchase statuses, backfills order totals and adds policy/quote tables. Migrations 001–015 remain unchanged. Existing PO statuses and stock remain unchanged; existing orders do not retroactively require approval. The default Compose configuration still uses your existing PostgreSQL container.

English/Urdu labels and RTL are included for new screens. Browser verification uses a single-connection PGlite harness; real PostgreSQL concurrency, Docker startup and production deployment remain unverified. External integrations, offline sync, multi-store stock, complex promotions, native apps and the other CHECKLIST.md gaps remain implementation work.
