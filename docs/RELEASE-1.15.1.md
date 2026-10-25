# StockDesk frontend hotfix 1.15.1 — request IDs over HTTP

The browser restricts crypto.randomUUID to secure contexts (HTTPS and trusted local origins). An EC2 IP address or domain served over ordinary HTTP can therefore work for login/catalog reads but throw `crypto.randomUUID is not a function` before submitting checkout. This frontend fix uses native randomUUID when available and a cryptographically random UUID-v4 fallback based on getRandomValues otherwise. It does not use Math.random or timestamps for payment request IDs.

All 12 direct calls across checkout, held bills, inventory adjustments, purchasing, payables, supplier returns, tills, catalog imports, customer credit actions, stock counts, invoice adjustments and split-payment row IDs now use the shared helper. Existing pending request IDs remain reused for retries. Checkout request-ID generation is inside its error-handling block.

## Patch an existing EC2 installation without upgrading other modules

From this package, copy only `scripts/fix_pos_uuid.py` into your existing StockDesk project root (the directory containing frontend and compose.yaml). The self-contained script works with the existing 1.14/1.15 frontend source; it adds the helper and replaces the affected calls in that source. It retains original changed files under uuid-hotfix-backup. A second successful run changes zero calls. It does not alter .env, Docker networking, API contracts or database migrations.

```bash
python3 fix_pos_uuid.py .
docker compose build frontend
docker compose up -d --no-deps --force-recreate frontend
```

If you use a differently named Compose file, use your usual `-f` option for both commands. Do not delete database volumes. After the container starts, hard-refresh with Ctrl+Shift+R or reopen the page so the browser loads the new hashed JavaScript bundle. Replacing source files without rebuilding the frontend image will not change files served by nginx.

The full package includes this hotfix on top of 1.15. Installing the entire package on a version older than 1.15 still requires its normal upgrade/migration steps; the patch script alone requires no migration or backend restart.

For production, serve the application over HTTPS to protect sessions and payment/customer data. When switching URLs, set APP_ORIGIN to the exact browser origin and COOKIE_SECURE=true for HTTPS, then recreate the backend with those environment settings. This HTTP compatibility patch does not provide TLS.

## Validation

Four request-ID tests cover native invocation, fallback UUID shape/uniqueness across 10,000 generated IDs, version/variant bits and explicit unsupported-browser errors. Production TypeScript/Vite build passed. Browser acceptance exercises actual POS checkout/receipt, hold/resume and import with randomUUID disabled; a separate non-local HTTP-origin browser probe confirms isSecureContext=false, randomUUID absent and the getRandomValues fallback working. No EC2 deployment was accessed or changed by this test.
