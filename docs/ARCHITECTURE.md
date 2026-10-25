# Architecture and retail scope

## Current implementation

StockDesk is a modular monolith with an independent FastAPI service and React client. PostgreSQL owns the inventory ledger. The frontend is a consumer, not the source of business rules. Another trusted server or native client can authenticate with an expiring bearer token and call the JSON API without rendering React.

- `app/api/contracts.py`: validated public write contracts; reject unknown fields; fractional quantity contracts are limited to three decimals, with whole-unit validation in the domain.
- `app/api/retail.py`: database lookups, customer credit, installment schedules, batch alerts, held bills and tills.
- `app/features/credit.py`: immutable credit ledger, repayments, schedules and return reversal.
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
| Weighed goods / scales | Base decimal quantities and money rounding implemented; pack conversion, scale protocols and variable-weight barcode parsing still required |
| Perishables | Batch/expiry and FEFO implemented; recall workflows, category policies and vendor/physical acceptance still required |
| Inventory counts | Blind count sessions, count snapshots, variance approval, adjustments against concurrent movements |
| Purchasing maturity | Supplier editing/archive, approval limits, expected dates, goods-receipt reversals, supplier returns, invoice matching and payables |
| Forecast integration | Outstanding PO deduction implemented; add supplier lead distributions, stockout-censored demand, replenishment per location, model monitoring |
| Checkout operations | Basic cashier tills and held bills implemented; add split tenders, partial returns, manager overrides and hardware integration |
| Promotions and loyalty | Price books, effective dates, rule precedence, mix-and-match, loyalty balances and customer consent |
| Offline operations | Device identity, signed local journal, sync/idempotency, stock conflict policy and recovery drill; offline is not browser caching alone |
| Payments and fiscalization | Gateway adapters and reconciliation, hardware terminals, local tax/fiscal invoice adapter and jurisdiction-specific acceptance |
| Public integrations | OAuth/OIDC service principals with scopes, key rotation, webhook outbox/delivery retries, dead-letter replay and versioned event schemas |
| Operations | OpenTelemetry, structured log sink, SLOs, load tests, backup restoration drills, failover and RPO/RTO agreed for the deployment |
| SaaS lifecycle | Subscription billing, quotas, tenant onboarding, data export/retention, admin support controls, SSO/MFA and security review |
| Large catalogs | Server-side search/cursor paging throughout the UI, scan lookup endpoint, query plans, reporting read models and storage budgets |

Deploy this release as a single-stock-location inventory/POS with weighted units application after acceptance testing. It is not yet a full grocery chain platform or a certified fiscal POS. Do not add microservices before operational boundaries and measured bottlenecks justify them.

See RELEASE-1.3.md for the authoritative current scope and operating constraints.

## 1.3 boundaries

`features/taxation.py` owns deterministic discount allocation and tax calculations, shared by quote and checkout. `api/taxes.py` owns tenant tax administration. Tax snapshots and tender parts are persisted with the same sale transaction. `src/i18n.ts` owns language state and literal translation; backend data values remain stable. Urdu fonts are self-hosted. Tenant-scoped fixed-role authorization remains unchanged; custom/scoped roles are not implied by these changes.


## 1.4 stock-count concurrency

Movement-triggered product revisions fence count snapshots. Posting holds the tenant transaction lock, checks every captured revision first, then writes batch deltas and completion audit atomically. A count cannot be approved by its creator. Management reports read consistent snapshots and derive exact included-tax exclusions from invoice snapshots.


## 1.5 finance and importing

Supplier ledger transactions use the tenant lock shared with goods receiving. Received minus previously posted bill quantities fences matching. No stock or cost revaluation occurs when billing/paying. Voids retain documents and audit records. CSV preview uses a rollback savepoint under tenant authorization; commit replays the same product rules and atomically stores import deduplication.


## 1.6 authorization

Each request resolves an active membership and any tenant-bound custom role. EffectiveRole carries a per-request frozen permission set; tenant grants never modify the global built-in role map. Legacy/versioned endpoints share authorization and cost redaction. Role writes serialize with other tenant mutations. Owner/role/team administration is excluded from the assignable capability catalogue. Application audit reads use a separate capability and UTC paging/filtering.


## 1.7 supplier stock/finance boundary

New receiving writes a structured movement-to-receipt/batch link atomically. Supplier returns reference these sources and the original billed purchase, enforce both lifetime source capacity and current aggregate batch stock, and commit stock, credit and audit together. All operations use the tenant lock. Credit allocation uses cumulative bill-line rounding; invoice totals and gross receipt quantities are immutable. Payments, credits and refunds form a derived signed balance. Legacy free-text movement notes are not inferred as provenance.


## Purchasing controls (1.8)

The existing tenant lock serializes order creation with policy updates and approval/receiving. A policy snapshot and rounded PO total are stored before line insertion in the same transaction. Decision authorization is separate from stock access and forbids the original actor. Receipt code accepts only open/partial status. Supplier quotes use optimistic versions; writes validate supplier/product tenancy and unit precision. Performance reads use a repeatable-read snapshot and first receipt per PO, never a join that multiplies receipt samples by line count. No new background jobs or external messages are introduced.
