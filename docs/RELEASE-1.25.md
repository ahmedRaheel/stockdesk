# StockDesk 1.25 — refunds to original payment methods

This release completes recorded original-payment refund allocation where payment evidence is available. It does not complete the entire enterprise checklist, currency conversion, statutory credit notes, adjustment reversals or external provider settlement.

## Workflow

In **Sales & receipts → Return / exchange**, select returned quantities and optionally replacement items. Enable **Refund to original payment methods**, then preview. Credit first reduces outstanding invoice debt under the existing khata rules. Remaining credit is allocated proportionally across the unconsumed recorded payments, including later recoveries assigned to this invoice. Allocation uses integer minor units and largest-remainder rounding; no floating-point money calculations.

The preview separates cash from each external payment source. Record exactly one refund reference per non-cash source after confirming that refund outside StockDesk. Confirming commits the invoice adjustment, source consumption, replacement tender provenance, cash movement and audit evidence atomically. Cash refunds require an open till with sufficient cash. External amounts do not reduce till cash, and no provider is called. Request retries reuse the recorded result.

Original-method settlement applies when no additional amount is due from the customer. If replacement items cost more than available credit, use the existing cash or external collection flow. New adjustments through those flows also record payment-source consumption and preserve replacement credit provenance when the underlying evidence permits it.

## Provenance and caps

Each adjustment consumes only its available credit, after debt reduction. The consumed amount is split between the actual refund and credit carried to the replacement invoice. Later adjustments cannot consume the same source twice. Replacement tender rows identify carried credit separately from newly collected money; they preserve their original payment method and origin reference for subsequent returns. A carried cash-origin credit does not add fresh cash to the till.

Invoice-specific payment allocations identify khata recoveries. New recoveries freeze method name, Urdu name and cash classification at collection time. Migration 032 initializes those fields for existing recoveries from their currently configured method; it cannot recover labels that were changed before this upgrade. Changing payment sources or recovering more money after preview invalidates the quote.

An invoice with earlier adjustment credit lacking source evidence, older generic exchange credit, or missing collection records cannot use automatic original-method settlement. The API/UI explain the limitation and retain manual cash/external settlement. The application does not invent historical payment allocations.

## Receipts and reporting

Adjustment confirmation, receipt history and English/Urdu PDF invoices show each recorded refund amount and external reference. Replacement receipts identify carried return credit. Operational till reports distinguish carried tender credit from fresh cash while keeping previously frozen Z reports unchanged.

## API and deployment

Preview accepts `original_methods` (default false). Commit accepts `settlement: original` and `refund_references: [{source, reference}]`; the flag must match the selected settlement mode. Preview returns `payment_allocation` with availability, consumed sources, refunds, transfers and cash_refund. Committed results retain `source_usage`, `refunds` and `cash_refund`. Source IDs come from the quote; clients must not invent them.

Existing cash/external clients remain supported. Previously committed requests preserve replay compatibility by omitting new default fields from their stored signature comparison. Pending pre-upgrade adjustment approvals/quotes should be recreated because the reviewed payload now includes payment-allocation evidence.

Migration 032 adds frozen recovery method fields, carried-credit/origin fields on sale tenders and the new settlement enum value. Migrations 001–031 and the external PostgreSQL/Docker setup remain unchanged. No dependencies are added. No live EC2 or provider acceptance is claimed.
