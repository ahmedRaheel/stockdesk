# Verification record — StockDesk 1.21

## Release 1.21 checks

- Full backend regression: **77 passed, 1 skipped** in 139.30 seconds under PGlite. After adding disabled-approver-account enforcement, the two transaction-control integration tests passed again in 12.34 seconds. The skipped test still requires real PostgreSQL multiprocess concurrency.
- Batch/khata coverage includes explicit lot allocation across successive returns, invalid/duplicate/excess allocations, original stock reconciliation, installment paid-versus-credited values, latest-installment-first credits, recovery-after-preview rejection, final refunds, full-return markup waiver and idempotent adjustment retries. Existing exchange, cash, tax, promotions, role and credit suites also pass.
- Approval coverage includes separate policy switches and stale versions, owner-only configuration, mandatory enforcement on checkout/full returns/partial adjustments, self-approval denial, changed transaction/other actor denial, one-time use with safe checkout replay, expiration, rejection, disabled accounts, membership revocation, tenant isolation, malformed nested payloads and CSRF.
- Chromium against React/FastAPI passed Owner policy setup, POS discount request, separate Manager approval, unchanged checkout, selected-batch refund approval/confirmation, khata return approval/zero-cash debt credit, and Urdu/mobile review. Native randomUUID was disabled in the cashier browser; no JavaScript page errors. The test uses separate browser processes because this Chromium build shares session state across contexts in a single process. Earlier test selectors were corrected for combined status text and duplicate Refresh controls.
- TypeScript/Vite build, literal Urdu coverage and four request-ID tests pass. OpenAPI regenerated for 1.21. Migrations 001–025 compared byte-for-byte with the saved 1.20 archive and remain unchanged. New migrations 026–027 add schedule credits and transaction approvals; no dependencies or deployment configuration changes.
- Tests use PGlite with a test-only single-connection pool. No live EC2/Docker deployment, real PostgreSQL multiprocess/load, hardware or regulatory acceptance is claimed. This release delivers the three documented transaction-control features; the other enterprise modules remain open and the latest exclusions are recorded in the checklist.


## Release 1.20 checks

- Full backend regression: **75 passed, 1 skipped** in 123.92 seconds under PGlite. The skipped test still requires real PostgreSQL multiprocess concurrency. Quiet-hours/feedback/alerts focused tests: **6 passed** in 17.66 seconds.
- Quiet-hour tests cover overnight start/end boundaries, all-day windows, invalid endpoints, deferral without replaying cleared conditions, existing-alert resolution and escalation suppression. Feedback tests cover strict rating/note contracts, invoice linkage and tenant isolation, duplicate retries/conflicts, status filters/summary, stale updates, resolve/reopen audit, unauthorized Cashier access and CSRF.
- Chromium against React/FastAPI passed quiet-hour create/edit/defer/release and feedback record/resolve/reopen with native randomUUID unavailable. Desktop and Urdu/mobile screens reviewed. Rating fractions use explicit left-to-right isolation in RTL; textareas provide three lines. No JavaScript page errors.
- TypeScript/Vite build, literal Urdu coverage and four request-ID tests pass. OpenAPI regenerated for 1.20. Migrations 001–024 were checked against the authoritative 1.19 archive and are unchanged; migration 025 is new. No dependencies added. An initial TypeScript check caught a time-string conversion in the severity change handler; it was restricted to payload serialization.
- Existing deployment/network configuration is unchanged. PGlite tests are not production PostgreSQL concurrency/load, AWS/Docker, hardware or regulatory acceptance. Full enterprise completion is not claimed; docs/COMPLETION-ROADMAP.md orders outstanding work.


## Release 1.19 checks

- Full backend regression: **73 passed, 1 skipped** in 119.30 seconds under PGlite. The skipped test requires real PostgreSQL multiprocess concurrency. Focused alerts suite: **4 passed** in 12.19 seconds.
- New coverage includes strict escalation bounds, critical-rule rejection, before/at-deadline behavior, one-time escalation/audit, acknowledged-alert suppression, resolution-before-escalation, recurrence, rule edits, worker evaluation, tenant isolation, escalated filtering and retained history. Initial tests caught and corrected an extra argument in the product validation query.
- Chromium against React/FastAPI passed rule create/edit, overdue critical status, escalated-only filtering, acknowledgement and replenishment/resolution with retained escalation history. Desktop/Urdu mobile screenshots reviewed; no JavaScript page errors. Browser native randomUUID was unavailable throughout, preserving the EC2 HTTP fallback check.
- TypeScript/Vite production build, literal Urdu coverage and four request-ID tests pass. OpenAPI regenerated for 1.19. Migration 024 is new; migrations 001–023 are unchanged. No dependencies added.
- Full tests and browser use PGlite; production pool settings are unchanged. Real PostgreSQL multiprocess/load, live EC2/Docker deployment, hardware/provider acceptance and the broader enterprise checklist remain unverified or outstanding.


## Release 1.18 checks

- Full backend regression: **71 passed, 1 skipped** in 113.62 seconds using PGlite. The skipped test requires real PostgreSQL multiprocess concurrency. Focused promotion regression: **9 passed** in 17.94 seconds.
- Automatic-selection coverage includes tax-inclusive final-total comparison (a smaller pretax discount can win), deterministic ties, inactive/future/minimum-spend exclusion, explicit-only exclusion, customer/global caps, failed checkout rollback, duplicate request replay, stale quotes, return history, no eligible offer, held-bill persistence and the 100-active-offer bound.
- Chromium against actual React/FastAPI passed manager create/edit, POS selection, hold/resume, cash checkout, receipt and exhausted-offer fallback. Urdu/mobile and desktop screenshots reviewed; no JavaScript page errors. Native randomUUID was unavailable throughout the browser flow, exercising the HTTP-compatible helper.
- TypeScript/Vite build, literal Urdu coverage and four request-ID tests pass. OpenAPI regenerated for 1.18. Migration 023 is new; migrations 001–022 unchanged. No dependencies added.
- Tests use the existing PGlite harness; browser pooling is test-only. No live EC2/Docker deployment, real PostgreSQL multiprocess/load or hardware/provider certification is claimed. The broader checklist remains open as documented.


## Release 1.17 checks

- Full backend regression: **70 passed, 1 skipped** in 107.71 seconds under PGlite. The skipped test requires real PostgreSQL multiprocess concurrency. Promotion-focused tests: **10 passed** in 18.13 seconds.
- New coverage includes strict cap validation, active/tenant customer boundaries, customer-bound quote tokens, failed-payment rollback, exhausted-cap/stale-quote rejection, idempotent replay, returns preserving usage, cap increases/decreases, unlimited-period history and independent global caps. Sales-only custom-role tests verify customer selection without financial fields or credit endpoint access.
- Chromium against React/FastAPI passed cap creation/edit, required-customer errors, successful cash checkout, exhausted-customer rejection, switching to an eligible customer, Urdu/mobile and HTTP UUID fallback. No JavaScript page errors. Desktop and mobile screenshots reviewed. The browser uses a test-only single-connection PGlite pool; production settings are unchanged.
- TypeScript/Vite build, literal Urdu coverage and four request-ID tests passed. OpenAPI regenerated for 1.17. Migration 022 adds caps and customer redemption attribution; migrations 001–021 unchanged. No new dependencies.
- No live EC2/Docker deployment, real PostgreSQL multiprocess/load or hardware/provider acceptance is claimed. This completes per-customer promotion limits; other gaps remain in docs/CHECKLIST.md.


## Release 1.16 checks

- Full backend regression: **68 passed, 1 skipped** in 103.37 seconds under PGlite. The skipped test requires real PostgreSQL multiprocess concurrency. Final cross-product suite: **2 passed** in 6.61 seconds after the inactive-component disable/reactivate safeguard.
- Coverage includes role/order independence, whole-unit validation, discount caps, mixed inclusive/exclusive tax, tenant boundaries, checkout replay, frozen original promotion after live edits, unrelated returns, partial-pair rejection, full-pair refunds, restored stock and unchanged redemption count.
- Chromium against React/FastAPI passed promotion creation/edit, POS quote/checkout, receipt/PDF download, rejected partial-pair return, full-pair cash refund and Urdu/mobile checks with crypto.randomUUID unavailable. No JavaScript page errors. Mobile screenshot and rendered PDF reviewed.
- TypeScript/Vite production build, literal Urdu coverage and four request-ID tests pass. OpenAPI regenerated for 1.16. Migrations 001–020 remain unchanged; migration 021 is new. No dependencies added.
- Real PostgreSQL multiprocess/load, live EC2/Docker deployment and hardware/provider acceptance remain unverified. This completes the bounded cross-product BOGO checklist item; broader enterprise gaps remain in docs/CHECKLIST.md.



## Frontend hotfix 1.15.1

- Four request-ID tests pass, covering the native path, secure random fallback, 10,000 UUIDs, exact version/variant bits and unsupported-browser errors. TypeScript/Vite production build passes.
- Browser checkout, receipt/change, held-bill resume, promotion selection, supplier statement and catalog import exercise the fallback with randomUUID explicitly unavailable. A separate ordinary HTTP-origin probe confirms the browser itself omits randomUUID and the fallback still generates valid UUID v4 IDs.
- All 12 application call sites use the helper. The self-contained patch script was applied to a clean copy of the previous frontend and rerun to verify idempotence. Existing request retry semantics are preserved. No new dependency, backend behavior or migration.
- The 66-pass/1-skip backend regression below belongs to 1.15; backend tests were not rerun for this frontend-only patch. No live EC2 deployment was accessed.

## Release 1.15 checks

- Full backend regression: **66 passed, 1 skipped** in 98.85 seconds using PGlite's PostgreSQL wire adapter. The skipped test still requires real PostgreSQL multiprocess concurrency.
- Catalog-focused suite: **7 passed**. Coverage includes editable XLSX roundtrip, literal formula-like names and leading-zero identifiers, exact decimal money, rollback-only previews, stale metadata/token rejection, unchanged inventory under simultaneous stock movements, retained active/medical/tax fields, idempotent retries, mode conflicts, duplicate/missing SKU, immutable units, opening-stock guard, barcode conflicts, tenant/role boundaries, CSRF and bounded/no-store exports.
- Promotion-focused suite passed before the full run, with the full run additionally covering API weekday/overnight create/update persistence. Pure tests cover Karachi weekday/date anchoring, after-midnight eligibility, start-inclusive/end-exclusive boundaries and invalid/empty/duplicate weekday contracts. Existing discounts, tax, usage-limit and quote-version tests remain passing.
- Chromium against actual React/FastAPI downloads editable Excel, reimports it, displays no-change and changed-field previews, commits updates without changing stock, and creates/loads a Sunday-only 22:00–02:00 offer. Urdu/mobile screens and dynamic success-notice translation reviewed; no JavaScript page errors. The browser uses the existing test-only single-connection PGlite pool.
- TypeScript/Vite production build and literal Urdu coverage pass. OpenAPI regenerated for 1.15. Migrations 001–019 are unchanged; migration 020 adds weekday data and overnight-window support. No new dependencies.
- Initial tests caught the need to exclude the stock revision counter from preview invalidation. That was fixed; stock and stock_revision remain untouched. A browser selector exposed an ambiguous textarea label after loading CSV; an explicit accessible label was added. Production Docker, real PostgreSQL load/concurrency, external integrations and full enterprise completion remain unverified or unimplemented as recorded in CHECKLIST.md.

## Release 1.14 checks

- Full backend regression: **63 passed, 1 skipped** in 95.43 seconds using PGlite's PostgreSQL wire adapter. The skipped test requires real PostgreSQL multiprocess concurrency. Final focused adjustment/PDF regression: **4 passed** in 7.47 seconds after the batch-restocking safeguard and receipt fixes.
- Adjustment coverage: original-price tax/discount credit, repeated partial/final returns without rounding loss, original checkout replay, request-id conflict/retry, stale revision, expired/damaged/opened non-sellable stock, incorrect-item restocking, expired-batch and ambiguous multi-batch restock rejection, excessive quantity, inclusive tax, failed replacement atomic rollback, no-open-till rejection, equal-value exchange, net till collection/refund, over-tender/change, external references, original/revised PDF, cost redaction, cashier denial, tenant isolation and CSRF.
- Chromium against actual React/FastAPI exercises exchange preview, extra cash/change, revised receipt/PDF, original receipt/PDF link, pure cash refund and Urdu/mobile. The test-only PGlite pool is single-connection; production settings remain unchanged. Screenshot and revised PDF render reviewed. The original-PDF snapshot timestamp/string fallback was fixed after an explicit original-download regression test. Initial browser assertions were corrected for currency formatting, cash-input accessible name and asynchronous original-receipt loading.
- TypeScript/Vite production build and literal Urdu coverage pass. OpenAPI regenerated for 1.14. Migrations 001–018 remain byte-identical to the preceding package; migration 019 is new. No dependency added.
- This is current-invoice revision accounting with preserved snapshots, not a statutory credit-note ledger. Partial khata, payment provider settlement, original-tender refund routing, independent refund approvals, real PostgreSQL multiprocess/load, production Docker and hardware acceptance remain outstanding. See CHECKLIST.md and RELEASE-1.14.md.

## Release 1.13 checks

- Full backend regression: **61 passed, 1 skipped** in 89.70 seconds using PGlite's PostgreSQL wire adapter. The skipped test requires real PostgreSQL multiprocess concurrency.
- New contract/API coverage includes invalid thresholds and expiry windows, tenant-bound product references, duplicate rule names, low-stock default reorder thresholds, repeated evaluation without duplicate events, acknowledgement/retry preservation, condition clearance and recurrence, disabling rules, optimistic edit conflicts, expiry boundary inclusion, worker due checks, suspended-tenant skipping, inactive-product resolution, tenant isolation, Cashier denial and CSRF rejection.
- Browser against actual React/FastAPI with ALERT_WORKER_ENABLED=true created a rule and waited for an automatically generated event without manual evaluation, then acknowledged it, replenished stock, evaluated resolution and inspected Urdu/mobile UI. The extended flow also exercises reports/downloads, cash change, supplier statements, promotions, held bills and Excel import. The test-only PGlite browser pool remains single-connection; production pool settings are unchanged.
- The initial API test identified a route collision with the existing batch alert summary. New endpoints were moved to `/alert-center`, preserving the original `/inventory-alerts` API. An initial browser run stopped at an ambiguous Refresh selector; the test was scoped to the alert-center button. Raw enum labels found during visual review were replaced with readable English/Urdu labels.
- TypeScript/Vite build and literal Urdu coverage passed for the implementation. OpenAPI regenerated for 1.13. Migrations 001–017 are byte-identical to 1.12; migration 018 is additive. No new dependency.
- Real PostgreSQL multi-process alert contention, high-load evaluation, production Docker startup, external messaging/delivery and full checklist completion are not claimed. The worker's locking/deduplication mechanisms are implemented; production acceptance remains necessary.


## Release 1.12 checks

- Final full backend regression: **59 passed, 1 skipped** in 83.30 seconds under PGlite. Real PostgreSQL concurrency is the skipped test.

- Focused report/turnover tests: **7 passed**. Coverage includes fractional daily-average stock, zero stock, net returns, invalid stock history, literal formula-like identifiers, leading zeros, numeric major-unit money, frozen headers/filter range and explicit export bounds.
- API acceptance exercises all ten export datasets in both formats, turnover opening/closing values, return-date semantics, empty other-tenant data, invalid query/format/name, no-store responses, cost-permission denial and cross-tenant denial.
- Chromium against actual React/FastAPI downloaded management and turnover Excel/PDF files and passed turnover navigation/Urdu/mobile checks, alongside cash, supplier statements, promotions, hold/resume and catalog-import regressions. No JavaScript page errors. The browser uses the existing test-only single-connection PGlite pool.
- Downloaded workbook previews were rendered with artifact-tool and inspected; PDF pages and desktop/390px RTL UI were inspected. Numeric formatting and export-button styling were improved after the first visual pass. Product identifiers stay text; exported snapshots contain no formulas. No native Excel/physical A3 printer acceptance is claimed.
- TypeScript/Vite production build and literal Urdu coverage passed. OpenAPI regenerated for 1.12; migrations 001–017 are unchanged. No new dependency.
- Initial full run encountered one connection reset while starting the cash test against PGlite (58 passed, 1 skipped otherwise). No production code was changed to hide that failure; the fresh full run passed as recorded above.
- Real PostgreSQL multiprocess concurrency/load, production Docker/nginx startup, external services and full checklist completion remain unverified/incomplete.


## Release 1.11 checks

- Full backend suite: **57 passed, 1 skipped** in 83.58 seconds under PGlite's PostgreSQL wire adapter. Real PostgreSQL multiprocess concurrency remains skipped.
- New cash acceptance test verifies over-tender, exact payment, one-cent shortfall rejection, split cash/external payment, khata cash change, saved receipt fields, English/Urdu invoice generation, stable idempotent response, net cash totals and failed-checkout rollback. Credit-enabled customer state is seeded explicitly for the khata case; approval behavior remains covered by the existing retail suite.
- Supplier statement assertions verify posted refund inclusion, voided refund exclusion, exact final balance, English/Urdu PDF responses, invalid language, missing/cross-tenant supplier denial and finance-permission denial.
- Chromium actual React/FastAPI flow passed excess cash entry and live change, saved receipt change, supplier statement link/download, plus the promotion/hold/resume/Excel regression workflow with no JavaScript page errors. Cash receipt and English/Urdu invoice/statement PDF renders were visually inspected. A missing receipt row layout class found in visual review was corrected before the final browser run.
- TypeScript/Vite production build and literal Urdu coverage passed. OpenAPI regenerated for 1.11. Existing migrations through 017 are preserved; no new migration/dependency.
- Browser database harness uses a test-only single-connection pool. Production Docker/nginx startup, real PostgreSQL load/concurrency, physical receipt printing and live deployment remain unverified. Full checklist completion is not claimed.


## Release 1.10 checks

- Full backend regression: **56 passed, 1 skipped** in 77.76 seconds using PGlite's PostgreSQL wire adapter. The real PostgreSQL concurrency test remains skipped.
- Promotion coverage includes exact discount allocation and mixed taxes, BOGO and repeated/weighted bundles, date/time and usage limits, optimistic edits, stale quotes, atomic failed checkout, idempotent retries, frozen invoice history, return usage policy, held codes, permissions and tenant isolation.
- XLSX coverage includes text identifiers/leading zeros, invalid formulas/numeric barcodes, oversized ZIPs, macros/external links, extra rows/columns, spoofed dimensions, template download, conversion without writes, preview rollback, atomic commit/replay and permission denial.
- Chromium against actual React/FastAPI passed promotion form creation (BOGO, percentage, bundle), POS quote, hold/resume, checkout, frozen receipt, Excel preview/commit and Urdu/mobile navigation without JavaScript page errors. Desktop and 390px RTL screenshots were inspected. Browser PGlite uses a test-only single-connection pool; production settings are unchanged.
- Urdu promotional invoice PDF rendered and visually inspected. Excel template rendered and visually inspected, then parsed and imported through the API/browser workflows.
- TypeScript/Vite production build and literal Urdu locale check passed. OpenAPI regenerated for 1.10. Original migrations 001–016 remain byte-identical to the supplied archive; migration 017 is additive.
- Real PostgreSQL multiprocess concurrency/load, Docker/nginx startup, live deployment, external integrations and physical hardware remain unverified. These checks do not establish full checklist completion or production certification.

## Release 1.9 checks

- Full backend regression run: **47 passed, 1 skipped** using PGlite's PostgreSQL wire adapter. The real PostgreSQL concurrency test remains skipped.
- After adding the final Urdu statement test and language/tenant API assertions, the focused operational-report and PDF suites passed **7 tests**. This includes four pure analytics tests, one database API flow, and two PDF tests; these overlap the full run and are not seven additional unique tests.
- Analytics tests exercise frozen mixed inclusive/exclusive taxes, manual legacy taxes, corrupt-snapshot rejection, fractional half-up stock values, expiry boundaries, deduplicated baskets and exact denominators, minimum pair counts, zero-sales/zero-demand scenarios and independent demand/price/cost assumptions.
- Actual API flow checks report totals against a historical sale, current stock valuation before/after a whole return, empty second-tenant results, Cashier/cross-tenant denial, query bounds, Urdu statement delivery, invalid-language rejection and cross-tenant customer access denial.
- Chromium against actual FastAPI/React: tax register invoices, stock and basket navigation, CSV download, demand scenario recalculation, English/Urdu and 390px RTL mobile passed with no JavaScript page errors. Desktop/mobile screenshots inspected. Browser-only PGlite harness uses a single-connection pool; production pool configuration is unchanged.
- Urdu customer statement rendered to PNG and visually inspected. A wrapped date found in the first rendering was fixed by widening the date column. Multi-page statement generation is tested; no physical printing is claimed.
- TypeScript/Vite production build and literal Urdu label check passed. OpenAPI regenerated for 1.9. Original migrations 001–016 were byte-compared against the supplied ZIP and remain identical; no new migration is needed.
- The first database attempt could not reach a server in a separate execution network. The successful run starts database and tests together in one harness. This is a test-environment limitation, not a production database validation.
- Live deployment, real PostgreSQL concurrency/load, provider integrations and physical hardware remain unverified. This release does not establish full checklist completion or production certification.


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
