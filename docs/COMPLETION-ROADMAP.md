# Remaining completion roadmap after 1.21

The requested full enterprise scope is not complete. The checklist's missing column is authoritative. The following is dependency order, not a promise that these modules exist or a calendar estimate.

1. **Transaction controls:** safe promotion stacking, original-tender refund allocation and adjustment reversal. Version 1.21 delivers independent manual-discount/return approvals, partial khata adjustments and batch-specific returns. Acceptance must cover retries, concurrent approvals, rounding, tax and stock/ledger invariants.
2. **Catalog and inventory foundations:** product variants, serials, pack conversion, kits/BOM, locations, transfer lifecycle, warehouse permissions and receipt-layer costing/landed costs. Existing tenant-wide stock requires a migration and reconciliation plan before store-level operations.
3. **Multi-store and offline:** store hierarchy, local pricing/tax, cashier/device identity, offline data storage, idempotent sync protocol and explicit conflicts/oversell rules. Requires failure/reconnect and multi-device acceptance, not just a browser cache.
4. **Finance and CRM:** statutory credit-note/general ledger model, supplier advances/bank reconciliation/approvals, loyalty/wallet/gift-card liabilities, memberships/campaigns, khata reminders and recovery workflows. Local tax and credit policies must be confirmed before claiming regulatory behavior.
5. **Integrations:** provider-backed payment/refund settlement, outbound notification jobs and delivery receipts, accounting/e-commerce/delivery connectors, webhooks and e-invoicing. Select providers, obtain sandbox accounts/credentials, implement signed callbacks/retries and reconcile external outcomes before production acceptance.
6. **SaaS/security/operations:** SSO/MFA, support consent, subscriptions/metering, white-labeling, backups and verified restore, monitoring and deployment acceptance. Never infer compliance or uptime from unit tests.
7. **Reporting/AI and clients:** custom/scheduled/consolidated reports, advanced valuation/tax reports, validated forecasting and anomaly models, native apps and full dynamic translations. Predictive modules require suitable data and measured quality.
8. **Physical/external acceptance:** named printer/scale/drawer/scanner models, camera scanning, payment terminals, production-like PostgreSQL concurrency/load, AWS deployment and disaster recovery drills. Record actual evidence per environment.

External dependencies are not the only outstanding work: substantial independent software implementation remains in stages 1–7. Continue against CHECKLIST.md and mark only delivered, tested behavior implemented.

## Scope exclusions accepted for 1.21 onward

Provider-backed payment/notification/accounting/e-commerce work, device-specific hardware integrations and native clients are excluded by the user. Web/PWA work stays in scope. Excluding external dependencies does not complete the independent modules in stages 1–7; those still require implementation and testing.
