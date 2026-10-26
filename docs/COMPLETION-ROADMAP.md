# Remaining completion roadmap after 1.26

The requested full enterprise scope is not complete. The checklist's missing column is authoritative. The following is dependency order, not a promise that these modules exist or a calendar estimate.

Version 1.24 adds supported-browser camera entry, tenant-restricted cashier PIN sessions, and operational X/Z evidence. Tax-authority fiscal requirements, unsupported-browser decoding and the remaining areas below are not completed by those additions.

1. **Transaction controls:** currency conversion, statutory credit notes and adjustment reversal. Version 1.25 delivers recorded original-payment refund allocation, including split tenders, invoice recoveries and traced replacement credit; older ambiguous payment history remains manual. Version 1.23 adds explicit-code promotion stacking. Version 1.21 delivers independent manual-discount/return approvals, partial khata adjustments and batch-specific returns. Acceptance must cover retries, concurrent approvals, rounding, tax and stock/ledger invariants.
2. **Catalog and inventory foundations:** Version 1.26 adds bounded, values-only legacy XLS catalog import. serials, locations, transfer lifecycle, warehouse permissions and receipt-layer costing/landed costs. Version 1.22 delivers SKU variant families, explicit pack/unpack and stocked-output BOM assembly. Existing tenant-wide stock requires a migration and reconciliation plan before store-level operations.
3. **Multi-store and offline:** store hierarchy, local pricing/tax, cashier/device identity, offline data storage, idempotent sync protocol and explicit conflicts/oversell rules. Requires failure/reconnect and multi-device acceptance, not just a browser cache.
4. **Finance and CRM:** statutory credit-note/general ledger model, supplier advances/bank reconciliation/approvals, loyalty/wallet/gift-card liabilities, memberships/campaigns, khata reminders and recovery workflows. Local tax and credit policies must be confirmed before claiming regulatory behavior.
5. **Integrations:** provider-backed payment/refund settlement, outbound notification jobs and delivery receipts, accounting/e-commerce/delivery connectors, webhooks and e-invoicing. Select providers, obtain sandbox accounts/credentials, implement signed callbacks/retries and reconcile external outcomes before production acceptance.
6. **SaaS/security/operations:** SSO/MFA, support consent, subscriptions/metering, white-labeling, backups and verified restore, monitoring and deployment acceptance. Never infer compliance or uptime from unit tests.
7. **Reporting/AI and clients:** custom/scheduled/consolidated reports, advanced valuation/tax reports, validated forecasting and anomaly models, native apps and full dynamic translations. Predictive modules require suitable data and measured quality.
8. **Physical/external acceptance:** named printer/scale/drawer/scanner models, camera scanning, payment terminals, production-like PostgreSQL concurrency/load, AWS deployment and disaster recovery drills. Record actual evidence per environment.

External dependencies are not the only outstanding work: substantial independent software implementation remains in stages 1–7. Continue against CHECKLIST.md and mark only delivered, tested behavior implemented.

## Scope exclusions accepted for 1.21 onward

Provider-backed payment/notification/accounting/e-commerce work, device-specific hardware integrations and native clients are excluded by the user. Web/PWA work stays in scope. Excluding external dependencies does not complete the independent modules in stages 1–7; those still require implementation and testing.
