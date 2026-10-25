# StockDesk — Python SaaS Inventory & Point of Sale

A runnable full-stack application: **FastAPI + PostgreSQL + React/TypeScript + Plotly**.
Independent headless API and retail operations UI. PostgreSQL is the source of truth.

**Version 1.10** adds server-enforced coupons, percentage/fixed discounts, BOGO and multi-product bundle pricing, date/daily-time restrictions, redemption limits, frozen invoice promotion details, and Excel catalog import with preview/atomic commit. Open **Promotions and coupons** to configure offers, then select their codes in POS. See [release instructions](docs/RELEASE-1.10.md) and [implementation status](docs/CHECKLIST.md). The full enterprise specification remains incomplete.

## Upgrade your existing deployment

This release's default `compose.yaml` reuses your existing **postgres** container on **chatbot-network**. It does not start another database image. Keep a database backup and your original `.env` before replacing source files. Do not delete database volumes or edit previously applied migrations.

From `/mnt/c/stockdesk` in WSL:

```bash
# Use the actual database administrator if it is not postgres.
docker exec postgres pg_dump -U postgres stockdesk > stockdesk-before-upgrade.sql
```

If `stockdesk` has never been created, create it once instead (a dump of a nonexistent database will fail):

```bash
docker exec -it postgres psql -U postgres -d postgres -c 'CREATE DATABASE stockdesk;'
```

Merge these values into `.env`; keep your real credentials private:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_URL_ENCODED_DATABASE_PASSWORD@postgres:5432/stockdesk
POSTGRES_NETWORK=chatbot-network
ADMIN_EMAIL=your-admin@example.com
ADMIN_PASSWORD=YOUR_UNIQUE_12_TO_128_CHARACTER_PASSWORD
APP_ORIGIN=http://localhost:8080
COOKIE_SECURE=false
```

The password after `postgres:` is the existing PostgreSQL password; `/stockdesk` is the database name. `ADMIN_PASSWORD` is a separate application password. URL-encode special characters in the database password. In `.env`, single-quote values containing literal `$` to avoid interpolation. The configured bootstrap password does not reset existing accounts.

```bash
# Ensure an old exported shell variable does not override .env.
unset DATABASE_URL ADMIN_EMAIL ADMIN_PASSWORD POSTGRES_NETWORK
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml build
docker compose -f compose.yaml run --rm --no-deps backend python -m app.check_config
docker compose -f compose.yaml up -d --force-recreate backend frontend
docker compose -f compose.yaml logs --tail=100 backend
```

Open **http://localhost:8080**. Pending numbered migrations apply automatically on startup. The network declaration belongs under the top-level `networks:` key, not inside `services:`. Do not replace the database hostname with a fixed container IP. The supplied configuration assumes `postgres` is already attached to `chatbot-network`, as in your inspection output.

For a fresh installation, copy `.env.example` to `.env`, set credentials, and follow the same steps. To deliberately run a separate managed database instead, use `compose.managed.yaml` and set `POSTGRES_PASSWORD`; this is an optional alternative, not the default.

After signing in, create/select a business, manage its lookup lists, add products, and add staff. Staff creation does not send invitation emails.

## New controls

- Open **Tax configuration** to choose disabled, configured, or legacy manual tax. Add profiles, choose a default, and optionally assign product overrides. Read `docs/RELEASE-1.3.md` for rounding and effective-date rules.
- Switch **English / اردو** on login or in the top bar. Urdu invoice PDF downloads follow the selected UI language.
- Enable **Split payment** at checkout to record cash plus other methods. Gateway processing is not included.
- Use F2 for scanning focus, F4 for checkout and F8 to hold a bill. Buttons remain subject to validation.

## Implemented functionality

| Area | Features |
|---|---|
| SaaS | Isolated businesses; platform administrator; tenant owners; suspend/reactivate businesses |
| Accounts | Email/password login, Argon2 password hashing, HttpOnly session cookies, logout, password change, operator password recovery |
| Roles | Owner, Manager, Cashier, Stock Manager; authorization on every server operation |
| Purchasing | Suppliers, purchase orders, partial goods receipts, cancellation of outstanding quantities, duplicate-receipt prevention |
| Headless API | `/api/v1` catalog, stock, sales and purchasing; typed write contracts; OpenAPI; expiring bearer tokens; request IDs |
| Retail credit | Customer ledger, maker/checker credit approvals, partial payment, repayments, installments, promises, ageing and PDF statements |
| Lookups | Database-managed categories, units, payment methods and adjustment reasons, English/Urdu labels and inactive historical references |
| Batches | Fractional quantities to 3 decimals, batch receipts, FEFO sale allocation, expiry blocks, original-batch restoration on returns |
| Cashier | Server-held bills, resume at current prices, open/close till, cash movements and variance notes |
| Products | SKU and barcode uniqueness per business, category, selling price, purchase cost, reorder point, editing and archiving |
| Stock | Opening balance, IN/OUT adjustments, sale deductions, return restocking, searchable inventory, low-stock/out-of-stock alerts |
| POS | Search, barcode scanner entry, cart, quantity changes, fixed discount, percentage tax, cash/change calculation, externally collected payment recording |
| Invoices | Sequential invoice numbers per business, frozen prices and seller details, printable receipt, multi-page PDF invoice |
| Barcodes | Existing barcode field; Code128 PDF label generation; keyboard-wedge USB/Bluetooth scanners |
| Returns | Whole-sale return once; stock restoration, status change, audit history |
| Dashboard | Python-generated Plotly charts with hover/zoom/download; sales, stock value, product count, stock alerts |
| Predictions | Best/least sellers, daily/monthly history, demand trends, 7/30-day forecasts, stockout dates, reorder suggestions, CSV export |
| Reports | CSV export, latest 500 sales/movements, latest 100 audit entries |
| Delivery | Docker Compose, reverse proxy, migration checksums, health checks, unit/integration tests |

## Roles

| Permission | Super Admin | Owner | Manager | Cashier | Stock Manager |
|---|---|---|---|---|---|
| Manage businesses | Yes | No | No | No | No |
| View inventory | Yes | Yes | Yes | Yes | Yes |
| Create/edit products | Yes | Yes | Yes | No | Yes |
| Purchasing | Yes | Yes | Yes | No | Yes |
| Stock adjustments | Yes | Yes | Yes | No | Yes |
| POS and invoices | Yes | Yes | Yes | Yes | No |
| Forecasts and analytics | Yes | Yes | Yes | No | Yes |
| Return a sale | Yes | Yes | Yes | No | No |
| Manage staff | Yes | Yes | No | No | No |
| Business settings/audit | Yes | Yes | No | No | No |

Owner membership cannot be demoted/disabled through this UI, preventing accidental removal of the last owner. Staff can belong to more than one business with different roles. Disabling membership removes access only to that business. Existing account passwords are never changed by adding a membership.

## Purchasing and receiving

Open **Purchasing**, add a supplier, then create a purchase order with one or more catalog products. An order does not change stock. Use **Receive / details** to enter actual units delivered; partial deliveries leave outstanding quantities. Repeating an unchanged receipt after a response interruption returns the first result without adding stock twice. Over-receiving is rejected and the entire receipt rolls back. **Cancel remainder** closes unreceived quantities without undoing stock already received.

The UI shows 50 orders per page and the first 200 suppliers by name. Supplier editing/archiving and supplier returns are not implemented. Costs are captured on purchase lines; receiving does not automatically revalue inventory. Supplier lead times are stored for reference; forecast lead time remains a manual input.

## Forecasts and sales analytics

Open **Forecasts** from the sidebar. Owners, Managers, Stock Managers and platform admins can access it. Rankings support today, yesterday, the last 7 complete days, the previous Monday–Sunday week, this month, last month and the last 30 complete days. All boundaries use UTC. Daily and monthly tables show units and gross product sales before invoice discounts/tax; monthly history covers the retrieved 120-day window, so the first and current months can be partial.

The page includes best/least sellers (including zero sellers), rising/declining demand, current out-of-stock items, slow movers, projected stockout dates, excess stock above 90 days of expected sales, and restock quantities. Trend comparisons always use the latest 7 complete days against the preceding 7. Archived products remain in historical rankings but are excluded from forecasts. Whole-sale returns remove the sale from these historical metrics.

Forecasts begin tomorrow and use up to 90 complete days after product creation, with zero-sale days included. Products need at least 14 complete days and 3 selling days; otherwise the UI displays **Insufficient history**. The baseline is the last 28 days' average. With enough history, a weekday average from 8 weeks is compared using a 7-day holdout. The lower-error method is selected. WAPE is shown when the holdout contains sales; quality is Low or Moderate. These are baseline estimates, not guaranteed demand or calibrated confidence intervals. Variation ranges are heuristic.

Set supplier lead time, target stock coverage and safety percentage. Suggested reorder quantity is `ceil(daily forecast × (lead days + coverage days) × (1 + safety %) − current stock − outstanding purchase quantities)`, floored at zero. Stockout dates simulate the next 30 forecast days against current stock, without new deliveries. Products already out of stock are flagged immediately. Reorder suggestions subtract outstanding quantities on open/partially received purchase orders. They do not place orders automatically or assume delivery dates for stockout predictions. Use **Adjust stock** only when stock physically arrives or an adjustment is needed.

Forecasts reflect observed sales; they cannot recover unmet demand during stockouts and do not model promotions, holidays, price changes or supplier delays. Predicted sales value uses current selling price before discounts/tax. Review low-evidence estimates before purchasing. The CSV export includes product-level predictions and evidence.

## Barcode scanner setup

Use a scanner configured as a **USB HID keyboard** or **Bluetooth keyboard** with **Enter/CR as the suffix**. Focus the POS search input, scan the product barcode, and the app adds the matching item when Enter arrives. Repeated scans increase the cart quantity up to the displayed stock limit. Unknown barcodes remain in search and add nothing.

A product's SKU is also scannable. The optional barcode field can contain an existing EAN/UPC or other printable ASCII code. **Barcode label** generates a printable Code128 PDF using the stored barcode, or the SKU if no barcode is supplied. This does not allocate official EAN/GS1 identifiers. Camera scanning and vendor-specific serial/SDK devices are not implemented.

## Invoice and payment behavior

- Money is stored as integer minor units (for example, PKR 100.50 is 10050).
- Tax supports disabled, configured per-product/default profiles, or legacy manual entry. Rates use basis points; tax rounds half up. See the release guide for mixed inclusive/exclusive calculations.
- Discount is a fixed amount applied before tax.
- Invoice numbering is sequential within a business: `INV-0000001`.
- The sale snapshots its seller name/address/tax number/currency and product prices/names. Later edits do not rewrite the invoice.
- Cash checkout requires sufficient cash received and displays change.
- “Paid externally” records a payment already collected outside the system. There is no card gateway or automatic charge.
- A whole-sale return restores stock exactly once. The money refund must be handled externally.
- Invoice PDFs embed DejaVu Sans and Noto Naskh Arabic, with Urdu shaping. Customer-statement PDFs remain English. Jurisdiction-specific fiscal invoice rules are not implemented.

## Transaction and tenant safety

Each write uses a PostgreSQL transaction and locks its tenant row. This deliberately serializes writes within a business: it is straightforward for a small/medium store and prevents concurrent checkout, role changes and price changes from racing. Product rows are also locked at checkout. A database trigger applies stock ledger inserts; a CHECK constraint rejects negative stock. Sale, lines, movements and audit entries commit or roll back together.

Tenant IDs supplied by the browser are never trusted as authorization. Every operation checks session identity and active membership; every record query includes tenant scope. Composite foreign keys prevent cross-tenant sale items and ledger relationships. Platform admins have explicit cross-business access.

Checkout and manual adjustments use request IDs. Retrying an unchanged submission in the same open page does not duplicate it. Check transaction history before recreating an uncertain order after closing/reloading the page. No offline POS or browser-local source of truth is used.

## Local development

Use PostgreSQL 16 and Python 3.12. Create a disposable local database and configure:

```bash
export DATABASE_URL='postgresql://user:password@localhost:5432/stockdesk'
export ADMIN_EMAIL='your-admin@example.com'
export ADMIN_PASSWORD='your-unique-strong-password'
export APP_ORIGIN='http://localhost:5173'
export COOKIE_SECURE='false'
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to FastAPI on port 8000. Windows PowerShell users should set environment variables with `$env:NAME='value'` and activate `.venv\Scripts\Activate.ps1`.

The checked-in frontend lockfile makes JavaScript installs reproducible. Python direct dependencies are pinned; transitive dependencies may vary between installs.

## Tests

```bash
cd backend
python -m pytest -q
```

The integration test is skipped without `TEST_DATABASE_URL`. To run it, use a **disposable database**:

```bash
TEST_DATABASE_URL='postgresql://user:password@localhost:5432/stockdesk_test' python -m pytest -q
```

Tests cover validation, integer totals, roles, login/logout, tenant isolation, products, stock deductions, duplicate submissions, insufficient stock, returns, invoice snapshots, PDFs, barcode labels, membership changes, suspension, CSRF and password changes.

Do not point tests at a business database. Tests create a test admin and business records. A PostgreSQL concurrency test is included separately. Run it against real PostgreSQL before a production release with `RUN_CONCURRENCY=1 TEST_DATABASE_URL=... python -m pytest -q`.

## Operator tasks

Change your password using the shield button in the top bar. For forgotten passwords, run from a trusted server shell:

```bash
docker compose exec backend python -m app.reset_password user@example.com
```

It prompts without echoing the new password and revokes existing sessions. No email reset flow or self-service sign-up is included; the platform admin creates businesses, and owners create team accounts.

Before Internet deployment, use HTTPS, set `APP_ORIGIN` to the exact public origin and `COOKIE_SECURE=true`, restrict database access, configure backups, and run the real PostgreSQL acceptance/concurrency tests. Migration SQL is automatically applied under an advisory lock; never edit an applied migration. Add a new numbered SQL file for future changes.

Backup example:

```bash
docker exec postgres pg_dump -U postgres stockdesk > stockdesk-backup.sql
```

Restore into a separate empty database and verify before replacing any live system.

## Scope and limits

This release is an operational foundation, not completion of the full enterprise feature list. See [the release matrix](docs/RELEASE-1.3.md) before rollout. There is one stock location per business and fixed server-enforced roles. Inventory valuation uses current product cost, not FIFO costing or weighted-average cost. FEFO is physical batch allocation only. Catalog snapshots still load the full catalog; large-store performance has not been established.

English/Urdu operational labels, RTL layout and invoice PDFs are supported. Some dynamic errors, chart labels, exports and customer-statement PDFs remain English; see the explicit localization bounds in the release guide. No offline financial transactions or automatic synchronization are implemented.

Use HTTPS, real PostgreSQL concurrency tests, restore drills and store acceptance testing before real trading. External integrations, physical hardware output and jurisdiction-specific compliance require separate work. See `VERIFICATION.md` for checks actually performed.
