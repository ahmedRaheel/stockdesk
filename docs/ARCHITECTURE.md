# Architecture and retail scope

## Current implementation

StockDesk is a modular monolith with an independent FastAPI service and React client. PostgreSQL owns the inventory ledger. The frontend is a consumer, not the source of business rules. Another trusted server or native client can authenticate with an expiring bearer token and call the JSON API without rendering React.

- `app/api/contracts.py`: validated public write contracts; reject unknown fields and fractional unit quantities.
- `app/api/router.py`: versioned catalog, sales, inventory and purchasing resource endpoints.
- `app/features/catalog.py`, `inventory.py`, `sales.py`, `tenancy.py`: application commands.
- `app/features/purchasing/service.py`: suppliers, orders, partial receipts and cancellation.
- `app/service.py`: shared authorization, audit, command dispatch and the legacy workspace read model.
- `app/security.py`: Argon2, hashed opaque sessions, token issuance, throttling and Origin checks.
- `app/forecast.py`: deterministic baseline analytics with explicit evidence limits.
- `migrations/`: immutable, ordered, checksummed SQL changes.
- `src/Purchasing.tsx`: typed feature UI with independent remote state and receipt retry keys.
- `src/api.ts`: JSON client and normalized API failures.

The legacy workspace snapshot remains in use for dashboard, catalog reads and administration. It loads the full tenant catalog and bounded recent history. It is not a large-catalog read architecture. The new product endpoint supports bounded paging, but POS still uses the in-memory catalog. Existing frontend components still contain `any`; the whole codebase is not yet strict TypeScript.

## Consistency decisions

Writes lock the tenant before products. This protects checkout, membership changes, stock receipts and sequential invoice numbering with a simple lock order. Stock mutations insert ledger rows; a trigger updates product balances and a database constraint rejects negative stock. All sale or receipt side effects commit together. External payment collection is not inside this transaction.

Tenant serialization is suitable for an initial deployment, not an unbounded throughput strategy. Before a large-store rollout, benchmark realistic tills and change to narrower resource locks with a documented lock order. Separate invoice sequence allocation, repeat concurrency/fault tests and keep ledger constraints.

Purchase orders and receipts use caller-generated request IDs. Identical retries return the original result; different bodies with the same key fail. A partial delivery leaves an outstanding balance. Cancelling stops future receiving and preserves receipts already applied. Purchase costs are historical PO facts; receiving does not silently change catalog cost. This version has no supplier returns or accounts payable.

## Design system

Use the native platform sans-serif stack, 13–14 px operational text, tabular numerals, a charcoal navigation rail, neutral surfaces and a restrained blue action color. Stock states use labeled green/amber/red badges. Avoid decorative product placeholders dominating checkout. Keep primary actions predictable. Compact density changes table spacing; it does not reduce text sizes. Charts load independently of the main JavaScript bundle. No external font dependency.

Purchasing dialogs trap focus, restore the triggering control and support Escape. The older workspace dialogs need the same accessibility retrofit. A complete accessibility audit has not been performed.

## Delivery gates for grocery and large retail

The following are explicit remaining requirements, not features claimed in this package.

| Capability | Required implementation and acceptance gate |
|---|---|
| Branches, warehouses and bins | Stock balance per tenant/location/product; transfers with dispatch/receipt states; location-scoped permissions; reconciliation tests |
| Weighed goods / scales | Fixed-precision base quantities, UOM conversion, pack sizes, decimal rounding, scale protocols and variable-weight barcode parsing; hardware acceptance tests |
| Perishables | Batch/lot balances, expiry dates, FEFO allocation, waste reasons, recall traceability and expired-item checkout policy |
| Inventory counts | Blind count sessions, count snapshots, variance approval, adjustments against concurrent movements |
| Purchasing maturity | Supplier editing/archive, approval limits, expected dates, goods-receipt reversals, supplier returns, invoice matching and payables |
| Forecast integration | Subtract outstanding incoming purchase quantities, use supplier lead distributions, stockout-censored demand, replenishment per location, model monitoring |
| Checkout operations | Register/till shifts, cash opening/closing, drawer reconciliation, split tenders, held sales, partial item returns and manager overrides |
| Promotions and loyalty | Price books, effective dates, rule precedence, mix-and-match, loyalty balances and customer consent |
| Offline operations | Device identity, signed local journal, sync/idempotency, stock conflict policy and recovery drill; offline is not browser caching alone |
| Payments and fiscalization | Gateway adapters and reconciliation, hardware terminals, local tax/fiscal invoice adapter and jurisdiction-specific acceptance |
| Public integrations | OAuth/OIDC service principals with scopes, key rotation, webhook outbox/delivery retries, dead-letter replay and versioned event schemas |
| Operations | OpenTelemetry, structured log sink, SLOs, load tests, backup restoration drills, failover and RPO/RTO agreed for the deployment |
| SaaS lifecycle | Subscription billing, quotas, tenant onboarding, data export/retention, admin support controls, SSO/MFA and security review |
| Large catalogs | Server-side search/cursor paging throughout the UI, scan lookup endpoint, query plans, reporting read models and storage budgets |

Deploy this release as a single-stock-location, whole-unit inventory/POS application after acceptance testing. It is not yet a full grocery chain platform or a certified fiscal POS. Do not add microservices before operational boundaries and measured bottlenecks justify them.
