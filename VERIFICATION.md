# Verification record

## Passed
Final automated run: **24 passed, 1 skipped**. The skipped test requires a real PostgreSQL concurrency run.

- React/TypeScript type check and Vite production build.
- Chromium browser smoke against the actual React/FastAPI application and PGlite: login, catalog navigation, supplier creation, purchase creation, partial receiving, cash checkout and receipt display; no JavaScript page errors. Stock reconciled 24 → 27 → 26.
- Desktop catalog, purchasing and POS screenshots and a 390 px mobile POS screenshot visually inspected. Test data was synthetic and is not seeded into the delivered application.
- Python module compilation.
- Versioned API integration: bearer issuance/revocation, cookie CSRF, no invalid-token fallback to cookies, pagination, validation errors and OpenAPI schema.
- Purchasing integration: duplicate order/receipt keys, payload conflicts, cross-tenant supplier rejection, cashier denial, partial receipt, cancellation, completed receipt, over-receipt rejection, and rollback of a valid first line when a subsequent line fails.
- Plotly split into a deferred bundle: the main app build is about 277 kB before gzip; the chart runtime remains about 4.7 MB.
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
