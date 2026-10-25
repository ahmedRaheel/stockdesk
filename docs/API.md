# Headless API

Interactive reference: `/api/docs`; OpenAPI JSON: `/api/openapi.json`.

The API uses tenant IDs in resource paths. Every endpoint rechecks active membership, role permissions and business status. Never use a tenant ID as authorization. Money is integer minor units; quantities support up to three decimals for fractional units. JSON contracts reject unknown fields. Validation returns HTTP 422 with `error` and field paths. Business validation returns 400, forbidden access 403, missing records 404 and purchasing conflicts 409. Every processed response receives `X-Request-ID` for support correlation.

## Trusted server / native client

1. POST `/api/v1/auth/token` with `email` and `password`.
2. Send `Authorization: Bearer <access_token>` on later requests.
3. GET `/api/v1/tenants` to select an authorized business.
4. DELETE `/api/v1/auth/token` to revoke the current credential.

Tokens are opaque, stored only as hashes on the server, expire after the configured session lifetime, and are revoked when a password is changed. They inherit the user's current tenant roles. This is not OAuth, delegated consent, scoped integration keys or a refresh-token flow. Use HTTPS and secret storage; never put tokens in URLs or browser localStorage.

The supplied browser UI uses `/api/auth/login` with an HttpOnly cookie and exact Origin checks for writes. No cross-origin browser policy is enabled. Alternate browsers should use a same-origin reverse proxy. Requests with an Authorization header never fall back to cookies. The bearer login shares account-based throttling with browser login. Nginx also limits both login routes.

```python
import httpx

with httpx.Client(base_url="http://localhost:8080", timeout=30) as client:
    # Read these values from your own secret store or environment.
    import os
    response = client.post("/api/v1/auth/token", json={
        "email": os.environ["STOCKDESK_EMAIL"],
        "password": os.environ["STOCKDESK_PASSWORD"],
    })
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    businesses = client.get("/api/v1/tenants")
    businesses.raise_for_status()
    print(businesses.json())
    client.delete("/api/v1/auth/token").raise_for_status()
```

## Resources under `/api/v1/tenants/{tenant}`

| Method | Path | Purpose |
|---|---|---|
| GET | `/products?q=&limit=50&offset=0` | Search and page catalog, maximum 200 per page |
| POST | `/products` | Create catalog item and opening balance |
| PUT | `/products/{id}` | Full replacement of editable product attributes |
| POST | `/stock-adjustments` | Idempotent IN/OUT ledger adjustment |
| POST | `/sales` | Idempotent checkout with expected-total verification |
| GET | `/sales/{id}` | Frozen receipt data |
| POST | `/sales/{id}/returns` | Whole-sale return, at most once |
| GET, POST | `/suppliers` | List/create suppliers; GET supports limit and offset |
| GET, POST | `/purchase-orders` | Page/create orders |
| POST | `/purchase-orders/{id}/receipts` | Receive one or more product quantities, including partial delivery |
| POST | `/purchase-orders/{id}/cancel` | Cancel outstanding quantities; preserve received stock |

The full schemas are generated from the actual Pydantic contracts. Catalog creation is not idempotent by request ID; SKU uniqueness prevents duplicate products. Supplier creation is unique by tenant and name. Checkout, adjustments, purchase orders and receipts require `request`. Persist that identifier with an unchanged submission across retries; do not silently generate a new one after an uncertain result.

PDF routes and forecasts remain available at `/api/invoices/{sale_id}.pdf?tenant=...`, `/api/products/{id}/barcode.pdf?tenant=...`, and `/api/forecasts?tenant=...`. Administrative UI operations remain on the legacy workspace API. `/api/health` checks database readiness; `/api/live` reports process liveness.

## Retail resources added in 1.2

All paths below use `/api/v1/tenants/{tenant}`. Read exact fields and response contracts in generated OpenAPI.

| Methods | Path | Behavior |
|---|---|---|
| GET, POST | `/lookups` | Search/list by kind; create database reference data |
| GET, PUT | `/lookups/{id}` | Historical lookup read; edit display names/active/order, immutable code/kind |
| GET, POST | `/customers` | Customer search and registration |
| GET | `/customers/{id}/statement` | Running ledger, documents, installment and payment history |
| GET | `/customers/{id}/statement.pdf` | Download statement |
| POST | `/customers/{id}/promises` | Record payment promise |
| GET, POST | `/credit-requests` | Request enabled credit limit |
| POST | `/credit-requests/{id}/decision` | Approve/reject with maker/checker rule |
| POST | `/recoveries` | Idempotent repayment; `request`, `customer`, `amount`, `method`, `reference` |
| POST | `/installment-plans` | Schedule receivable with optional fixed markup |
| GET | `/credit-overview` | Ageing and scheduled dues; not a predictive risk model |
| GET | `/batches`, `/inventory-alerts` | Batch stock and expiry views |
| GET, POST | `/held-bills` | Cashier-owned server drafts |
| DELETE | `/held-bills/{id}` | Discard own unused draft |
| GET, POST | `/tills` | Own sessions and opening cash |
| POST | `/tills/{id}/cash-movements` | Idempotent signed cash record with reason |
| POST | `/tills/{id}/close` | Counted cash, variance note, repeated-close protection |

Catalog writes accept `category_id`, `unit_id`, `search_aliases`, `expiry_required`, `generic_name`, `strength` and `prescription_required`. Legacy category text must resolve to an active lookup. Unit is fixed after creation. Stock IN and purchase receipts accept `lot` and `expires`; OUT may target `batch_id`.

Checkout adds `customer_id`, `paid_now`, `due_date`, `payment_method_id`, `prescription_reference` and optional `held_bill_id`. `paid_now` is applied to the invoice, while `tendered` is the cash handed over including change. Invoice total remains the full sale value; credit amount is total minus paid now. Cash-mode and payment lookup must agree. Partial payment means paid-now plus receivable, not multiple payment tenders.

Product responses and receipt lines omit `cost` for roles without that permission. Customer ledger is append-only. Every credit, batch, sales and cash side effect runs in the tenant transaction. Holds and till openings have different retry semantics: a duplicate open till returns conflict; a held bill ID deduplicates an unchanged draft. Customer creation/credit requests/plan creation are not generic idempotent endpoints; inspect state after uncertain results.

## Tax quotes and split tenders (1.3)

- GET/PUT `/tax-settings`: mode (`manual`, `configured`, `disabled`) and default profile.
- POST `/tax-profiles`, PUT `/tax-profiles/{id}`: name/name_ur, rate_bps, inclusive, active, starts_on/ends_on.
- POST `/sales/quote`: items, discount, tax_bps; returns subtotal, tax, tax_included, total, line tax allocation and quote_token. This preview does not reserve stock.
- Product writes support nullable `tax_profile_id`; null inherits the business default.
- Checkout carries `quote_token` and optional `tenders` array of `{method_id, amount, reference}`. Sum of tenders must equal paid_now. Tendered cash must cover the cash subset.
- Receipt JSON adds `tenders`; sale adds `tax_included`, `tax_snapshot` and `cash_amount`. Tax snapshot is stored JSON. Invoice PDFs support `language=en|ur`.
- Return payload accepts nullable `reason_id` from return_reason lookups.
- Lookup writes accept nullable `fractional` for unit creation/editing. The rule cannot change after catalog use.

All configuration changes require settings permission and tenant write serialization. Preview requires sale permission and a consistent read transaction. Quotes cannot bypass checkout stock, credit, expiry or prescription checks.


## Version 1.4 endpoints

Tenant prefix `/api/v1/tenants/{tenant}` applies throughout.

- `GET/POST /stock-counts`: page counts or open an idempotent reference/product batch snapshot.
- `GET /stock-counts/{id}`: lines, current revisions and quantities.
- `PUT /stock-counts/{id}/lines`: creator saves draft counted quantities.
- `POST /stock-counts/{id}/submit`: all quantities required.
- `POST /stock-counts/{id}/post`: independent Owner/Manager posts with note, rejects changed stock revisions.
- `POST /stock-counts/{id}/cancel`: creator or authorized approver, reason required.
- `GET /management-report?days=30`: cost permission required; 1–90 complete days, Asia/Karachi, net/cost/profit and ABC/XYZ breakdowns.

See openapi.json for exact request fields. All mutation authentication/tenant/CSRF rules remain in force.


## Version 1.5 endpoints

Tenant prefix `/api/v1/tenants/{tenant}` applies.

- `GET/POST /payables`: paginated bill register/global current ageing or matched supplier bill creation.
- `GET /payables/matchable-orders?q=&offset=0`: database order lookup, 50 per page, received unbilled quantities.
- `GET /payables/{id}`: lines and payment history.
- `POST /payables/{id}/payments`: record external payment, idempotency key required.
- `POST /payables/{id}/void` and `/payables/{id}/payments/{payment}/void`: reasoned ledger corrections.
- `POST /catalog-imports/preview`: validate CSV using rolled-back creation rules.
- `POST /catalog-imports`: atomic new-product creation with request idempotency.

Finance permission is restricted to Owner/Manager; CSV import uses product permission. All write CSRF/tenant rules apply. Exact schemas and bounds are in openapi.json.


## Version 1.6 endpoints

Tenant prefix `/api/v1/tenants/{tenant}` applies.

- `GET /roles`: owner-only role records, supported capabilities and prerequisites.
- `GET /roles/members?q=&offset=0`: owner-only staff search, 50 per page.
- `POST /roles`, `PUT /roles/{id}`: create/version-checked update and disable.
- `POST /roles/assignments`: assign active custom role to an existing non-owner member.
- `GET /audit-events?q=&start=&end=&limit=50&offset=0`: separate audit capability; inclusive UTC dates, total and bounded page.

Custom permissions replace built-in permissions at authorization time. Role assignment does not reactivate staff. Membership/owner/role administration cannot be delegated. Schemas are in openapi.json.


## Version 1.7 endpoints

Prefix `/api/v1/tenants/{tenant}/payables/{bill_id}`.

- `GET /return-options?q=&offset=0`: receipt sources, stock and remaining billed/received quantities, 50 per page.
- `POST /returns`: source-bound physical return and original-bill credit in one transaction. Requires supplier_return permission and request ID.
- `POST /refunds`: record supplier money received against a credit balance; finance permission and request ID.
- `POST /refunds/{refund_id}/void`: reasoned correction, no external money transfer.

Bill detail now includes credited/refunded totals and credit/refund history; listing includes signed balance and summary supplier_credit. Positive outstanding and ageing exclude negative balances. Goods credits cannot be voided. Lookup kind supplier_return_reason is supported. See OpenAPI for exact contracts.


## Version 1.8 endpoints

Prefix `/api/v1/tenants/{tenant}`. Money is integer minor units; quantity supports up to three decimal places on writes.

- `GET /purchasing-policy`: stock permission; disabled/version 0 if not configured.
- `PUT /purchasing-policy`: owner-only, enabled/threshold/version, stale version 409.
- `POST /purchase-orders/{id}/decision`: purchase_approve, decision approve/reject and note, no self-decision. Matching repeated decision returns replayed=true.
- `GET /supplier-offers?q=&product=&quantity=1&eligible=false&offset=0`: 50 matches, product/price ordering, date and minimum-quantity eligibility.
- `POST /supplier-offers`, `PUT /supplier-offers/{id}`: stock permission, validated tenant references, unique supplier/product, versioned updates.
- `GET /supplier-performance?q=&offset=0`: stock permission, 50 suppliers, observed first-receipt metrics.
- `GET /suppliers` additionally accepts literal case-insensitive `q` search across name/contact.

Purchase-order reads now include order_total, approval_required, approval_threshold, lead_days_snapshot and decision fields. Legacy orders keep their status; pending/rejected orders cannot receive. Exact schemas are in openapi.json.

## 1.9 operational reports

`GET /api/v1/tenants/{tenant}/operational-report` requires `cost` permission. Query: `days` (1–90, default 30), `minimum_baskets` (2–10000, default 2), `horizon_days` (1–365, default 30), `demand_pct`, `price_pct`, `cost_pct` (integers -100–500, default 0). Returns `start`, `end`, `timezone`, `tax` (groups/invoices/summary), `stock` (as_of/batches/summary), `baskets`, and `scenario`. Money is integer minor units. The scope and accounting limitations are documented in RELEASE-1.9.md. All reads are tenant-bound and use a repeatable-read database snapshot.

`GET /api/v1/tenants/{tenant}/customers/{customer}/statement.pdf` accepts optional `language=en|ur`. Existing customer-credit permissions and tenant isolation apply.

## 1.10 promotions and Excel import

- `GET /api/v1/tenants/{tenant}/promotions`: bounded `q`, `limit` (1–100), `offset`; `include_inactive=true` requires `promotions`. Active lookup requires either `sale` or `promotions`. Returns rules, components, version and usage count.
- `POST .../promotions`: requires `promotions`; create an uppercase code and a rule (`fixed`, `percentage`, `bogo`, `bundle`). `value` is minor money except `percentage`, where it is basis points. `components` contain `product` and decimal `quantity`. All dates/times and bounds are in the generated OpenAPI contracts.
- `PUT .../promotions/{id}`: same full payload plus current `version`. Code is immutable; stale versions return 409. Set `active=false` to disable.
- `/sales/quote` and `/sales` now accept optional `promotion_code`. Promotional checkout requires the returned `quote_token` and manual `discount=0`. Send the original user input discount, not the computed promotional discount. The quote's `discount` and `promotion.line_discounts` are server-computed. Checkout freezes `promotion_snapshot` and records one redemption atomically.
- `/held-bills` accepts optional `promotion_code`; it is retained without reservation.
- `GET .../catalog-imports/template.xlsx`: authenticated `product` permission; returns the static Excel template.
- `POST .../catalog-imports/convert-xlsx`: authenticated `product` permission and CSRF origin/bearer rules. Body `{ "file_base64": "..." }`, maximum 1 MB decoded. Returns `csv_text` and `count`; pass the CSV to the existing `/preview` and commit endpoints. Conversion performs no writes. See release notes for input shape and rejection rules.

## 1.11 cash and supplier statement additions

Checkout responses (including idempotent retries) include `cash_received`, `cash_amount`, `change`, `paid_now` and `credit_amount` in minor currency units. Receipt `sale` includes derived `cash_received` and `change` from saved cash/tender values.

- `GET /api/v1/tenants/{tenant}/payables/suppliers/{supplier}/statement` returns supplier, dated entries with signed amounts/running balances, and final net payable.
- `GET /api/v1/tenants/{tenant}/payables/suppliers/{supplier}/statement.pdf?language=en|ur` downloads the same current posted ledger. Finance permission required; maximum 5,000 entries, otherwise 422. Missing/cross-tenant supplier is 404 after authorization.

## 1.12 turnover and export endpoints

- `GET /api/v1/tenants/{tenant}/inventory-turnover?days=30`: 1–90 complete days through yesterday, Asia/Karachi; cost permission; maximum 10,000 products. Fields include opening/closing stock, sold/returned/net units, average daily closing stock, period turnover and days per turn. Unavailable ratios are null.
- `GET /api/v1/tenants/{tenant}/report-export/{name}.{format}`: names `products`, `categories`, `cashiers`, `hours`, `tax-summary`, `tax-invoices`, `stock-age`, `basket-analysis`, `what-if`, `turnover`; formats `xlsx` or `pdf`. Supports days and existing operational query parameters. Same cost permission; output is regenerated and no-store. PDF >500 rows and Excel >10,000 rows return 422. Money in exports is major currency units, unlike JSON/CSV minor units.

## 1.13 inventory alert center

All routes below require `alerts` permission and tenant membership (or platform-admin access). Writes require same-origin CSRF and tenant serialization.

- `GET /api/v1/tenants/{tenant}/alert-center/rules`: rules and `worker_enabled`.
- `POST .../rules`: name, kind (`low_stock`, `stock_out`, `expiry`), optional product/threshold, expiry_days (0–365), severity (`info`, `warning`, `critical`), active. 201.
- `PUT .../rules/{id}`: same fields plus version; 409 on stale version. Resolves current episodes for the edited rule.
- `POST .../evaluate`: evaluate active rules now; returns evaluated/opened/resolved counts.
- `GET .../alert-center?status=open|acknowledged|resolved|all&limit=50&offset=0`: paginated inbox and total; maximum page size 100.
- `POST .../alert-center/{id}/acknowledge`: note, 1–500 characters. First acknowledgement is retained on retry; resolved events return 409.

The existing `/inventory-alerts` batch-summary API is unchanged.


## Invoice adjustments (1.14)

See [release contract and accounting behavior](RELEASE-1.14.md). Preview/commit/history/original endpoints live under `/api/v1/tenants/{tenant}/sales/{sale_id}/adjustments`. Use a fresh revision and quote token, and retain the request ID for retries. Monetary amounts are integer minor units. Cash settlement requires an open till. Partial khata invoices are not supported.
