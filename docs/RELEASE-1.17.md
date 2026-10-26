# StockDesk 1.17 — per-customer promotion limits

Promotions now have an optional per-customer redemption limit. A limited offer requires an active registered customer from the current business. The cashier selects that customer in POS; changing the customer refreshes the quote. Limits apply to every supported offer kind alongside global caps and schedules.

## Counting and enforcement

Each successful promoted invoice consumes one redemption for the selected customer. Counts are lifetime totals for that promotion ID, including purchases before a limit was added or while it was disabled. Migration backfills existing named-customer redemptions; historical walk-in sales cannot be attributed. Walk-in sales remain allowed for offers without a customer limit.

Checkout rechecks usage while holding the existing tenant write lock. Quotes do not reserve redemptions. Customer-limited quotes are bound to the selected customer. Failed transactions do not consume usage; identical retries return the original sale. Returns and invoice adjustments do not restore redemptions. Increasing the limit permits more uses; lowering it below an existing customer's count is rejected. Disabling a limit never deletes usage history. Duplicate customer records have separate allowances; identity verification and deduplication are outside this release.

## Permissions and API

Promotion create/update accepts `per_customer_limit`: null (default: unlimited) or an integer from 1 to 1,000,000,000. Quote requests accept `customer_id`; checkout already accepts it. Limited sales freeze the applicable cap and customer ID in the promotion snapshot.

`GET /api/v1/tenants/{tenant}/sale-customers?q=...&limit=50&offset=0` and `GET /api/v1/tenants/{tenant}/sale-customers/{customer}` require sale permission and expose only active customers' ID, name and phone. Credit endpoints retain their original financial permissions. Creating customers still requires the existing credit/customer permission.

## Upgrade

Back up PostgreSQL and preserve `.env`, then deploy backend and frontend together using README commands. Migration **022_customer_promotion_limits.sql** adds the optional cap, tenant-scoped customer references on redemptions, backfills existing named-customer sales and adds a lookup index. Migrations 001–021 are unchanged. The existing external `postgres` container and `chatbot-network` configuration remain; no dependencies added.

Automatic offers, stacking, independent discount approvals and other enterprise gaps remain in CHECKLIST.md. Production Docker/EC2 and real PostgreSQL multiprocess acceptance have not been performed here.
