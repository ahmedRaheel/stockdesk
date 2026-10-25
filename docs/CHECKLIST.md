# Consolidated implementation checklist — 1.8

“Implemented” describes the bounded behavior below, not every requested variant. Code is delivered; production deployment and physical/provider acceptance are separate.

| Area | Implemented in this package | Still missing from requested scope |
|---|---|---|
| POS entry | Keyboard-mode barcode/SKU reader, manual catalog/code entry, weighted quantities, F2/F4/F8, hold/resume | Camera QR decoding, hardware SDKs, scale/drawer control |
| Sales and payments | Cash/external payment recording, split tenders, khata balances, invoice/receipt PDF | Payment gateway charging/settlement, FX conversion, partial returns/exchanges and refund allocation |
| Returns | Whole-sale return with stock restoration and explicit refund handling | Partial product returns, exchanges, credit-note accounting |
| Discounts and promotions | Fixed invoice discount | Coupons, campaign rules, bundles, BOGO, happy hour, independent discount/void approvals |
| Tax | Tenant-configured profiles, inclusive/exclusive, effective dates, product override, frozen invoice tax | Compound/geographic/withholding tax, statutory filing/FBR/e-invoicing |
| Offline | Online operation; no claim of offline committed sales | Device identity, offline database, conflict policy, reliable auto-sync |
| Catalog | SKU/barcode, unit lookup, weighted units, categories, aliases, basic atomic CSV new-product import | Variants, serials, pack conversion, XLSX, update imports, recipes/BOM |
| Inventory | Ledger, FEFO batches, expiry, dated receiving, reasoned adjustments, approved batch counts | Multi-location, transfers, FIFO/LIFO valuation layers, landed cost, warehouse workflows |
| Procurement | Suppliers, POs, partial receiving, cancellation of remainder, receipt-bound billed-goods supplier returns (new receipts from 1.7), owner-configured independent PO approval, current supplier quotes/eligible price comparison, observed first-delivery metrics | Multi-stage/budget approval, historical/unbilled returns, RMA/replacement workflows, tiered price lists/pack or landed-cost comparison, portal, EDI/auto-send |
| Supplier finance (1.7) | Cumulative PO/received/billed quantity and exact cost matching; invoice register; partial payments; ageing; audited voids; goods-return credit notes and recorded supplier refunds | Price-only/cross-bill credit notes and credit reversals, advances, payable approvals, bank reconciliation, general ledger, supplier statement PDF |
| Khata and installments | Customer ledger, credit limit approval, partial credit, recoveries, due dates, schedules and statements | Guarantor/CNIC/photo workflow, predictive trust scores, automated reminders, markup/late-fee policy, recovery agent tracking |
| Cashier operations | Till opening, cash in/out, counted closing and discrepancy notes | Hardware cash drawer, full fiscal X/Z reports, PIN/biometric switching |
| Analytics | Sales dashboard/rankings, basic profit breakdowns, descriptive ABC/XYZ, CSV reports | Builder/scheduling, full tax reports, stock aging/turnover valuation, consolidated financials |
| Forecasting | Baseline demand/reorder, stockout/replenishment planning using available history and outstanding POs | Weather/festival models, optimization, probabilistic credit/cashflow, churn, supplier delay, shrinkage, basket recommendations, staffing, what-if |
| Alerts | Existing on-screen low-stock/expiry/forecast exceptions | Configurable rule engine, push/email/SMS/WhatsApp/Urdu voice, quiet hours, escalation, delivery/retry jobs |
| CRM | Customer records, purchase/credit workflows, reference segments | Loyalty points, wallet/gift liabilities, memberships, campaigns, feedback |
| Access and tenancy | Tenant-bound API/data references, built-in and custom tenant roles, immediate revocation, permission dependencies, searchable/page-exportable audits of implemented writes; independent credit/count/PO approvals | Store/region-scoped roles, regions/franchise hierarchy, multi-store scope, support consent/impersonation, portals, SSO/MFA |
| SaaS operations | Platform business management and suspension, headless endpoints, bootstrap/admin controls | Plans/subscriptions/metering, native apps, white-labeling, backup orchestration and tested restore, uptime evidence |
| Languages | English/Urdu UI and RTL, bundled fonts, shaped Urdu invoice PDFs | Full dynamic error/CSV/chart translation, Urdu statement PDF shaping, automatic Roman Urdu transliteration |
| Integrations | REST API, token/session controls; keyboard-reader support | Accounting/marketplaces/delivery, payment rails, notifications, webhooks, e-invoicing, printers/scales/RFID SDKs |

Tax/legal certification, GDPR/PCI-DSS compliance, 99.9% uptime, high-load scalability, real PostgreSQL multiprocess concurrency and physical hardware operation have not been certified by this package. The modules in the last column are implementation work, not switches waiting only for credentials.
