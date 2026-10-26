# StockDesk 1.21 — invoice and approval controls

This release implements partial khata corrections, explicit return-batch selection, and independent manual-discount/return approvals. It does not complete the broader enterprise checklist.

## Partial khata returns and exchanges

Sales & receipts now opens the item-adjustment workflow for both paid and khata invoices. The quote shows original-price return credit, debt reduction, any financing waiver, remaining invoice debt, credit available for settlement, and the final amount to collect/refund. Current-price replacement checkout and the original cash-change behavior remain.

Policy: return credit first reduces this invoice's outstanding subledger balance (including any agreed markup); it never pays another invoice. Any remaining credit funds replacement items or a refund. Replacement amounts exceeding that credit are collected immediately, rather than creating new khata debt. Partially returning an invoice does not automatically waive markup. Fully returning its remaining items explicitly waives any residual financing balance. Already collected financing charges are not automatically refunded. This is an application policy, not a statutory or contractual compliance determination.

Installment credits reduce the latest unpaid installments first. Original amounts/dates and actual paid amounts remain separate; the new `credited` amount reduces remaining dues. Recovery allocation, overdue checks and ageing account for these credits. Original receivable principal and agreed plan total remain historical values. Posted ledger entries are append-only. Receipt UI and English/Urdu PDFs include debt reductions/waivers in adjustment history.

Preview and confirmation use the existing tenant transaction lock and stale-quote check. A recovery between preview and confirmation changes the quote and requires review. Replays preserve the prior result. Inventory writes, invoice revision, subledger/schedule credits, replacement sale and cash settlement commit together or roll back together. Cash refunds require an open till with sufficient expected cash.

## Select returned batches

`GET /sales/{sale}/adjustments/batches` returns currently sold, not-yet-returned quantities by item, batch, lot and expiry. Each return line optionally accepts `batches: [{batch, quantity}]`. Explicit quantities must sum exactly to the requested return quantity, use distinct batches from this invoice/product, respect remaining sold quantities, and obey whole-unit rules.

The UI exposes batch quantities alongside each return line. Leaving all at zero retains automatic allocation. Partial restocking from multiple eligible batches requires explicit selection; non-sellable returns can be automatically allocated. Expired, damaged and opened goods cannot be restocked; expired source batches cannot be restored to sellable stock. Prior adjustments are deducted from their actual batch movements, including pre-1.21 adjustments. Committed history records allocated batch IDs/lots/quantities. This adds no new batch table and does not alter past movements.

## Independent approvals

The Transaction approvals page is available to sales users. Owners configure separate manual-discount and return/exchange approval requirements; both default off for existing businesses. Assign a second approver before enabling: an owner cannot approve their own request. Owners/Managers receive `discount_approve` and `void_approve`; custom roles can receive these with their documented permission dependencies.

- Cashiers request approval from the POS after entering the exact cart, manual discount, customer and payment details. Configured promotions do not require manual-discount approval.
- Returns/exchanges request approval after previewing and entering settlement details. The legacy full-return API is covered by the same return policy, preventing bypass.
- A different authorized user reviews the summary and approves/rejects with a note. Requesters can view their requests; approvers can view requests matching their approval capability.
- Approval expires 30 minutes after submission, binds the exact normalized transaction and requesting user, and is consumed once inside the transaction. Changes to quantities, payment data, discount, invoice, quote or settlement require a new request.
- Confirmation rechecks the approver's current permission. Revocation/disabled membership prevents use. Failed transactions roll back consumption. An already committed submission can be safely retried without consuming again.
- Policy edits use optimistic versions. Requests, decisions, policy changes and consumption are audited. Fresh requests can be made after rejection/expiration; interrupted request submissions reuse their ID.

API prefix: `/api/v1/tenants/{tenant}/transaction-approvals`.

- GET `/policy`; PUT `/policy` with `version`, `discount_required`, `void_required` (owner only).
- GET with bounded `limit`/`offset` for the permitted queue.
- POST with `request`, `kind=discount|return|adjustment`, optional `sale`, and the matching checkout/return/adjustment `payload`.
- POST `/{id}/decision` with `decision=approved|rejected` and `note`.
- Checkout, full return and adjustment confirmation accept optional `approval_id`.

## Upgrade and scope

Back up the existing PostgreSQL database and retain `.env`. Deploy backend and frontend together using README commands. New migrations: **026_return_schedule_credits.sql** and **027_transaction_approvals.sql**. Migrations 001–025 remain unchanged. No dependencies or Docker/network/database-container changes are introduced; the existing HTTP-compatible request-ID helper is retained.

Per the latest scope instruction, payment/notification/accounting/e-commerce providers, device-specific hardware integrations, and native Android/iOS/Windows clients are excluded. Web/PWA software work remains in scope. Other unfinished items remain explicitly listed in CHECKLIST.md and COMPLETION-ROADMAP.md; they are not represented by placeholders or simulated integrations.
