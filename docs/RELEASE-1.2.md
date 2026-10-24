# StockDesk 1.2 — retail and credit release

## What is implemented

| Area | Behavior |
|---|---|
| Lookups | Tenant-scoped database rows with stable IDs, code, English/Urdu label, active state and ordering. Category/unit/payment/reason forms read the API. Server validates kind, tenant and active status. Used rows remain available historically when disabled. Categories from existing catalogs are migrated. |
| Weighted goods | Up to three quantity decimals for fractional units such as kg/litre. Piece units reject fractions. Server uses Decimal and half-up line rounding into integer money units. One sales unit per product; units cannot be changed after creation. |
| Customers and khata | Customer contact/aliases/reference contact; immutable signed ledger; invoice receivables; partial payment at POS; required due date; enabled credit limit and overdue blocking. No CNIC/photo collection or trust scoring. |
| Credit approval | Staff submit requests, Owner/Manager approve or reject; a requester cannot approve their own request. Limit cannot drop below the current balance. Approval history is audited. Create a second authorized user for maker/checker decisions. |
| Recoveries | Idempotent payment posting; oldest-due document allocation and installment allocation; rejects overpayment; payment receipt in the UI; cash recovery adds to an existing cashier till. |
| Qist | Weekly, fortnightly or monthly schedules; exact integer allocation of the final total; month-end-safe dates; optional fixed markup constrained by credit limit. First due date cannot be past. One plan per receivable. |
| Statements | Running customer ledger, outstanding invoices, installments, payment history, promise dates, PDF statement. Ageing uses Asia/Karachi dates with 0–7, 8–30 and 31+ day groups. Contractual next-30-day dues are labelled as scheduled amounts, not predicted recoveries. |
| Batches and medicine | Lot/expiry on receipts and adjustments; expiry-required products need dated lots. Generic name, strength and prescription-reference flag. FEFO checkout skips expired batches. Whole returns restore original allocation. Expired/near-expiry alert lists. These controls are not regulatory certification. |
| Held bills | Server stores the cashier's product quantities/customer; no stock reservation. Resume uses current prices and revalidates stock at checkout. Consumed held bills cannot be sold again under a new request. Discounts, taxes and payments are not preserved on hold. |
| Tills | One open till per cashier/business; opening cash, cash sales, cash recoveries, manual cash IN/OUT with reasons; counted close and variance. A discrepancy requires a note. Closing is repeat-safe. |
| Payments | Database labels for cash, JazzCash, Easypaisa, Raast, bank and card. External payments are records of money collected elsewhere, not gateway processing or verified QR payments. A payment label must match the cash/external collection mode. |
| Forecasting | Existing daily/weekly/monthly sales analysis, baseline SKU demand, stockout estimates, slow movers, excess-stock and reorder suggestions. Open PO quantities now reduce suggestions; not a supplier arrival forecast. |
| Permissions | Existing fixed Owner/Manager/Cashier/Stock Manager roles; tenant scope enforced server-side. Product cost and receipt cost are omitted for cashiers in API responses, not only hidden in the UI. |

## Operational rules

1. Add categories and units in Lookup management. Fractional unit behavior is stored in the database (seeded kg/litre); changing a unit's label does not change its quantity rules.
2. For expiry-controlled products create zero opening stock, then receive dated batches. Migrated stock is placed in `UNTRACKED` batches; physically reconcile and add expiry data through controlled stock adjustments before enabling expiry-required behavior.
3. Open a till before trading if cash reconciliation is required. Checkout is still allowed without an open till for compatibility; such sales are not included in a later session.
4. To sell on khata, register the customer, submit and independently approve a credit request, select the customer at checkout, enter the paid amount and due date. Credit is blocked if overdue or above limit.
5. Create an installment schedule against the remaining invoice receivable. Markup is a fixed minor-unit amount, not an interest calculation. No late fees, waivers or automatic debt collection are performed.
6. Whole-sale returns cancel outstanding credit including plan markup. `external_refund_due` includes the original paid amount plus recorded recoveries. Pay the refund outside the application and record an explicit cash OUT if cash leaves the drawer. Return status does not automatically subtract drawer cash.
7. Holds do not reserve stock. Leaving the page or losing connectivity does not provide offline checkout. A hold is a server-side draft, not a completed sale.
8. Archive lookup rows instead of deleting them. Seeded codes are immutable; display labels can change. Protocol enums such as IN/OUT, cadence and workflow status remain fixed API values; database lookups govern business reference data.

## Remaining requested scope

| Requirement group | Still pending |
|---|---|
| POS | Offline sale/sync conflict engine; multiple simultaneous payment tenders; partial returns/exchanges; coupons, BOGO and promotion engine; automatic tax determination; transaction-level FX; refund gateway; touchscreen hardware certification. |
| Inventory | Multiple locations/warehouses, transfers, pack conversion, serials, BOM/recipes, audit/count workflows, supplier returns, landed-cost/FIFO/LIFO/weighted-average valuation. Batch FEFO is not financial FIFO. |
| Enterprise access | Custom roles, region/store scope, supervisor PIN/biometric, risky-action approval workflows beyond credit limits, consented support impersonation. |
| Purchasing/finance | Supplier portal, price comparison, automatic PO dispatch, three-way invoice match, payables, consolidated accounts, accounting integrations. |
| CRM | Loyalty, gift cards/wallet balances, memberships, marketing campaigns, customer portal, credit-risk model, configurable late fees/waivers. |
| AI | Holiday/weather models, forecast price rises, cash-flow probabilities, churn, supplier delay, shrinkage anomaly, basket recommendations, staffing and what-if optimization. Existing forecasts abstain when history is insufficient. |
| Alerts | SMS, WhatsApp, Urdu voice calls, push, quiet hours and escalation engines. Current expiry and credit alerts are in-app views only. |
| Pakistan localization | Complete Urdu/RTL interface and receipt shaping; FBR integration; legal tax/medicine rule configuration and DRAP workflows. No compliance claim is made. |
| Platform | Subscription billing/metering, feature plans, SSO/MFA, native mobile/desktop apps, white-label, automated backups/restore, audited uptime SLA, enterprise performance certification. |
| Hardware/integrations | Payment gateways, Raast QR verification, Bluetooth printer SDKs, scale/RFID/cash drawer SDKs, marketplaces, accounting systems, webhooks. Keyboard-wedge barcode scanners and browser/PDF printing are available. |

## Known bounds

The catalog snapshot is not suitable for an untested very-large catalog. Batch alert lists are capped at 200 each. Customer search returns 50 matches per page; narrow using name/phone/aliases. Customer statements and credit overview are currently unbounded per tenant/customer; large datasets require report pagination/jobs. Till access is cashier-owned, not a full management shift dashboard. Reports mix UTC sales windows with explicitly Pakistan-dated credit/expiry rules. Scope and date conventions must be standardized before multi-country deployment.

Migrations 001 and 002 are unchanged; new schema is additive in 003–007. Take a backup and test restoration before applying migrations to live data. Do not downgrade the application after applying them without a tested database restore.
