# StockDesk — Python SaaS Inventory & Point of Sale

A runnable full-stack application: **FastAPI + PostgreSQL + React/TypeScript + Plotly**.
Independent headless API and retail operations UI. PostgreSQL is the source of truth.

**Version 1.1** adds a restrained retail theme, versioned resource APIs, bearer authentication, supplier purchasing and partial goods receiving. See [API reference](docs/API.md) and [architecture / rollout scope](docs/ARCHITECTURE.md).

## Start with Docker

1. Install Docker with Docker Compose.
2. Copy `.env.example` to `.env`.
3. Replace `POSTGRES_PASSWORD`, `ADMIN_EMAIL` and `ADMIN_PASSWORD` with your own values. The admin password must contain at least 12 characters. Use a URL-safe database password.
4. Run:

```bash
docker compose up --build -d
```

5. Open **http://localhost:8080** and sign in with your configured admin account.
6. Create a business, select its currency, and optionally create its owner's account.
7. Add products, including SKU/barcode, opening stock, price, purchase cost and reorder point.
8. Add staff in **Team & roles**. Provide name and initial password for new accounts. Staff log in with email/password; no invitation email is sent.
9. Open **Point of sale**, scan/select products and complete a sale.

The database is stored in the `postgres_data` Docker volume. `docker compose down` preserves it; `docker compose down -v` deletes it.

## Implemented functionality

| Area | Features |
|---|---|
| SaaS | Isolated businesses; platform administrator; tenant owners; suspend/reactivate businesses |
| Accounts | Email/password login, Argon2 password hashing, HttpOnly session cookies, logout, password change, operator password recovery |
| Roles | Owner, Manager, Cashier, Stock Manager; authorization on every server operation |
| Purchasing | Suppliers, purchase orders, partial goods receipts, cancellation of outstanding quantities, duplicate-receipt prevention |
| Headless API | `/api/v1` catalog, stock, sales and purchasing; typed write contracts; OpenAPI; expiring bearer tokens; request IDs |
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

Set supplier lead time, target stock coverage and safety percentage. Suggested reorder quantity is `ceil(daily forecast × (lead days + coverage days) × (1 + safety %) − current stock)`, floored at zero. Stockout dates simulate the next 30 forecast days against current stock, without new deliveries. Products already out of stock are flagged immediately. Reorder suggestions do not subtract open purchase orders or place orders automatically. Use **Adjust stock** only when stock physically arrives or an adjustment is needed.

Forecasts reflect observed sales; they cannot recover unmet demand during stockouts and do not model promotions, holidays, price changes or supplier delays. Predicted sales value uses current selling price before discounts/tax. Review low-evidence estimates before purchasing. The CSV export includes product-level predictions and evidence.

## Barcode scanner setup

Use a scanner configured as a **USB HID keyboard** or **Bluetooth keyboard** with **Enter/CR as the suffix**. Focus the POS search input, scan the product barcode, and the app adds the matching item when Enter arrives. Repeated scans increase the cart quantity up to the displayed stock limit. Unknown barcodes remain in search and add nothing.

A product's SKU is also scannable. The optional barcode field can contain an existing EAN/UPC or other printable ASCII code. **Barcode label** generates a printable Code128 PDF using the stored barcode, or the SKU if no barcode is supplied. This does not allocate official EAN/GS1 identifiers. Camera scanning and vendor-specific serial/SDK devices are not implemented.

## Invoice and payment behavior

- Money is stored as integer minor units (for example, PKR 100.50 is 10050).
- Tax is a manually entered percentage stored as basis points. Half-cent ties round up.
- Discount is a fixed amount applied before tax.
- Invoice numbering is sequential within a business: `INV-0000001`.
- The sale snapshots its seller name/address/tax number/currency and product prices/names. Later edits do not rewrite the invoice.
- Cash checkout requires sufficient cash received and displays change.
- “Paid externally” records a payment already collected outside the system. There is no card gateway or automatic charge.
- A whole-sale return restores stock exactly once. The money refund must be handled externally.
- PDFs embed DejaVu Sans fonts. RTL Arabic/Urdu shaping and jurisdiction-specific fiscal invoice rules are not implemented.

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
docker compose exec -T db pg_dump -U stockdesk stockdesk > stockdesk-backup.sql
```

Restore into a separate empty database and verify before replacing any live system.

## Scope and limits

This is an inventory/POS SaaS application, not a complete ERP. Subscription billing, online card processing, multiple warehouses per tenant, batch/expiry tracking, partial returns, offline checkout, payroll and accounting integrations are outside this version. Each business currently has one stock location. Sales KPIs sum completed invoices including tax; returned invoices are excluded. Inventory valuation uses current purchase cost, not FIFO or weighted-average costing. The latest 500 receipts/movements are shown in the UI; all records remain in the database.

This release uses whole-unit quantities and one stock location per business. Weighed goods, scales, batch/expiry/FEFO, branch transfers, till shifts and offline checkout require further implementation. The catalog UI still loads the full business catalog; large-store scale has not been established. The supplied CI workflow runs tests against PostgreSQL, including optional concurrency checks; that workflow has not been executed here.

Production performance, external payment integrations and legal/fiscal invoice compliance need deployment-specific work. See `VERIFICATION.md` for checks actually performed.
