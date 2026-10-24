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
