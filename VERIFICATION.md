# Verification record — StockDesk 1.8

## Release 1.8 checks

- Full backend suite: **42 passed, 1 skipped** in PGlite. New purchasing coverage includes owner-only policy updates, threshold boundary and frozen policy, self-approval rejection (including Owner), cross-tenant decisions, approval replay/conflicts, receiving blocks before approval/after rejection, quote duplicate and whole-unit checks, validity validation, eligible quantity filters, price ordering, version conflicts, immediate role revocation and observed receipt counts.
- Chromium exercised actual React/FastAPI UI: owner policy enablement, separate buyer PO creation, hidden self-approval action, independent approval, receiving, supplier quote create/edit and eligible comparison, performance, English/Urdu and mobile. No JavaScript page errors. Browser SQL used a test-only single-connection pool because PGlite's socket adapter does not provide independent PostgreSQL sessions; production pool settings remain unchanged.
- TypeScript/Vite production build and literal Urdu coverage checked. OpenAPI 1.8 regenerated. Migration 016 is additive; migrations 001–015 are byte-identical to the delivered 1.7 archive.
- Real PostgreSQL concurrency remains skipped. Docker deployment, external services and hardware are not verified by these checks.


## Release 1.7 checks

- Full backend suite: **41 passed, 1 skipped** under PGlite. New tests cover receipt replay/provenance, source/billed quantity limits, excessive tax credit rejection, atomic invalid-source rejection, fractional cumulative credit rounding, changed request conflicts, credit-adjusted payment limits, supplier credit balances, partial refund/over-refund protection, refund correction replay, protected credited bills, tenant isolation and stock-only access denial.
- Focused supplier-return and retail checks were rerun after introducing the separate supplier-return reason family.
- Chromium actual API/UI flow: matched bill, partial payment, goods return, credit note, supplier refund, reasoned refund void and English/Urdu mobile screens passed without page errors. Desktop/mobile screens inspected.
- TypeScript build and literal locale coverage passed. OpenAPI regenerated. Migrations 001–013 preserved; 014/015 are additive.
- Real PostgreSQL concurrency remains skipped; production Docker/hardware/bank acceptance is not claimed.

## Release 1.6 checks

- Full backend suite: **40 passed, 1 skipped** under PGlite. Custom-role tests exercise cost redaction in legacy/versioned product and receipt APIs, existing-session grant changes/revocation, reserved Owner names, blocked team/role escalation, required capability prerequisites, protected Owner membership, cross-tenant assignment denial, optimistic version conflicts and restoring built-in membership.
- The focused custom-role test also covers audit permission denial, filtered totals, page bounds and invalid date ranges, and was rerun after the audit endpoint was added.
- Chromium: create role, automatic prerequisite selection, database member/role selection, assignment, English/Urdu mobile views, audit search/details and CSV download passed without JavaScript page errors. Desktop/mobile layouts inspected.
- TypeScript production build and literal Urdu coverage passed. OpenAPI regenerated. Additive migration 013 preserves 001–012.
- Real PostgreSQL concurrency remains skipped. Production load, Docker startup, external integrations and hardware acceptance remain unverified.

## Release 1.5 checks

- Full backend suite: **39 passed, 1 skipped** using PGlite. New supplier tests exercise received/unbilled limits, cost mismatch rejection, unique invoice numbers, duplicate/conflicting requests, partial payments, overpayment rejection, cross-tenant lookups, role denial, audited voids and unchanged stock. New CSV tests verify exact minor-unit parsing, preview rollback, full rollback on a later invalid row, duplicate barcode rejection, weighted stock and replay safety. After parser hardening the focused import suite passed again (2 tests).
- Chromium actual UI/API: supplier bill registration, database payment lookup, partial payment, payment void and English/Urdu mobile views passed without page errors. CSV preview and commit passed; the imported weighted product appeared in the inventory catalog. Screens visually reviewed.
- TypeScript production build and literal Urdu catalogue coverage passed. Dynamic data/errors remain outside locale coverage.
- Migrations 001–010 were preserved; 011/012 are additive. OpenAPI regenerated for 1.5.
- Real PostgreSQL concurrency remains skipped; Docker, production load, provider transfers and physical hardware are not verified.

## Release 1.4 checks

- Backend: 36 passed, 1 skipped in PGlite. New tests cover independent stock-count approval, idempotent post, fractional-unit rejection, cross-tenant isolation, stale revisions after net-zero movements, exact mixed included-tax profit, and ABC/XYZ history boundaries. Real PostgreSQL concurrency remains skipped.
- TypeScript, Vite production build and literal Urdu translation coverage passed.
- Chromium flow: manual exact code and fractional quantity, repeated scanner keyboard input, unknown code, stock bound, F4 checkout, count submission/self-approval UI, management reports, and Urdu/mobile POS. Physical readers are not tested.
- New migrations preserve prior migrations 001–009. OpenAPI regenerated for 1.4.

## Previous 1.3 checks

- Backend: 33 tests passed, one real-PostgreSQL concurrency test skipped in the PGlite run. Includes tax rounding/discount allocation, mixed inclusive/exclusive and disabled tax, effective-date blocking, changed-quote rejection, immutable invoice totals, cross-tenant profile rejection, split-tender exact sums, duplicate retry, cash-only till totals and fractional-unit immutability.
- Browser: actual React/FastAPI flow in Chromium exercised English/Urdu switching, RTL tax screen, weighted inclusive-tax checkout, Urdu receipt/PDF, then cash/bank split checkout. No JavaScript page errors. Desktop Urdu tax/receipt and mobile split receipt visually inspected.
- PDF: rendered and inspected Urdu invoice with joined glyphs, tax extraction, quantity/unit and bilingual synthetic data. Bundled Noto Naskh Arabic covers the Urdu catalogue's Arabic-block characters; licenses are included.
- TypeScript and production build passed. Literal translation coverage check passed; it excludes dynamic data/errors and does not establish exhaustive localization.
- Existing tests for stock, khata, FEFO, purchasing, auth, tenant isolation and forecasting remain in the suite.

## Not verified

Docker startup, normal PostgreSQL multi-process concurrency, live provider integrations, hardware output, accessibility audit, high-load performance, backup/restore operations and production availability were not verified. PGlite SQL testing does not establish real PostgreSQL concurrency behavior. No statutory, GDPR or PCI-DSS certification is claimed.

## Previous 1.2 verification record



## Release 1.2 checks

- Actual React/FastAPI Chromium smoke with synthetic data: login, catalog, lookup management, customer statement, opening till, weighted 1.25 kg cart, hold/resume, cash checkout and receipt. No browser JavaScript errors. Desktop khata/lookup/POS and desktop/mobile receipts visually inspected.
- Integration tests exercise tenant-bound lookup IDs and deactivation, whole-unit rejection, cashier cost redaction, customer registration/search, maker/checker credit approval, partial credit checkout, monthly schedules, exact recovery allocation, duplicate/conflicting submissions, overpayment rejection, customer PDF, return/debt cancellation and explicit refund due.
- Batch tests verify FEFO allocation, expired stock exclusion, prescription-reference requirement, original-lot restoration on return, and batch/product stock equality.
- Cashier tests verify duplicate till open rejection, automatic cash-sale/recovery totals, cash-out deduplication, required discrepancy notes, counted closing, cashier-owned held bills and single consumption.
- Forecast test verifies outstanding PO quantities reduce reorder suggestions without pretending undated stock has arrived.
- Upgrade smoke applied original migrations 001/002 to a disposable database, seeded legacy category/stock, then applied through 007. Product lookup IDs, category labels and batch/stock totals were preserved. This used PGlite, not the user’s actual database.
- TypeScript check and Vite production build pass. Python files formatted with Black, frontend with Prettier. OpenAPI regenerated from running contracts.

## Existing checks retained and rerun

Final 1.2 automated run: **30 passed, 1 skipped**. The skipped test requires a real PostgreSQL concurrency run.

- React/TypeScript type check and Vite production build.
- Chromium browser smoke against the actual React/FastAPI application and PGlite: login, catalog navigation, supplier creation, purchase creation, partial receiving, cash checkout and receipt display; no JavaScript page errors. Stock reconciled 24 → 27 → 26.
- Desktop catalog, purchasing and POS screenshots and a 390 px mobile POS screenshot visually inspected. Test data was synthetic and is not seeded into the delivered application.
- Python module compilation.
- Versioned API integration: bearer issuance/revocation, cookie CSRF, no invalid-token fallback to cookies, pagination, validation errors and OpenAPI schema.
- Purchasing integration: duplicate order/receipt keys, payload conflicts, cross-tenant supplier rejection, cashier denial, partial receipt, cancellation, completed receipt, over-receipt rejection, and rollback of a valid first line when a subsequent line fails.
- Plotly split into a deferred bundle: the main app build is about 313 kB before gzip; the chart runtime remains about 4.7 MB.
- Ten forecast tests: calendar windows, known demand and reorder calculations, sparse/new histories, zero sellers, current-day leakage, out-of-stock alerts, archived products, zero holdout sales, weekday alignment and all-time last-sale metadata.
- Forecast API response and cashier access denial exercised through the integration flow.
- Ten pure rule tests: integer inputs, money/tax rounding, permission checks, duplicate cart products, discount bounds and password length.
- FastAPI integration flow exercised against PGlite through a PostgreSQL wire-protocol adapter, using the actual asyncpg SQL and migrations. The flow covers login, authorization, tenant isolation, product creation, duplicate SKU rejection, Plotly chart JSON, checkout, request deduplication, insufficient-stock rejection, cashier return denial, PDF authorization, return/restock idempotency, barcode generation, adjustments, frozen invoice line details, membership updates, suspension, CSRF, password change and logout.
- Single-page invoice PDF visually inspected after embedding DejaVu Sans. A 90-line invoice generated five pages with repeatable table headers and page footers.
- Barcode label and invoice generation smoke tests.

## Not verified here
- Docker Compose startup (Docker is not available in the execution environment).
- Real multi-process PostgreSQL concurrency. The optional concurrency test is included and deliberately skipped in the PGlite run; PGlite is not equivalent to a normal multi-connection PostgreSQL server.
- Full browser regression/accessibility audit, physical barcode reader hardware, thermal printer output, and public deployment.

Run the supplied integration/concurrency tests against a disposable PostgreSQL 16 database and perform the README acceptance flow before using real inventory or payments.
