# StockDesk 1.13 — inventory alert center

## Configure and handle alerts

Open **Inventory alerts**. Owners, Managers and Stock Managers receive the new `alerts` permission; Owners can grant it to custom roles. Cashiers do not receive it. Alerts contain inventory information only, not customer/supplier finance or cost data.

Create a named rule for one product or all active products:

- **Low stock:** quantity at or below a fixed threshold, or leave the threshold blank to use each product's reorder level. Weighted thresholds support three decimal places.
- **Out of stock:** quantity equals zero.
- **Expiry:** batches with positive stock whose expiry date is on or before today plus the configured 0–365 day window, including already expired batches. Date comparisons use Asia/Karachi. Batches without expiry dates do not match.

Set information, warning or critical severity. Rules are independent, so overlapping rules can create separate alerts for the same product. Rule names are unique within a business. Limits are 50 rules per business (including disabled rules), 5,000 matching products/batches per rule and 50 inbox entries per page. A rule exceeding its match limit fails explicitly and rolls back that evaluation rather than silently dropping alerts.

Use **Evaluate alerts now**, or enable the worker below. Repeated evaluations update the same active episode without duplicating it. **Acknowledge** records the first actor, time and note; repeating the acknowledgement preserves that original note. It does not alter stock or resolve the condition. When the condition no longer matches, evaluation resolves the episode. A later recurrence creates a new episode and does not inherit an old acknowledgement. Inactive products cease matching on the next evaluation.

Editing or disabling a rule resolves its existing episodes with `rule_changed`; the edited active rule starts fresh episodes on the next evaluation. Updates require the current version and reject stale forms. There is no hard-delete endpoint. Open, acknowledged and resolved history remains searchable by status and paginated; rule edits, acknowledgement and state transitions are audited. The screen refreshes its inbox every 30 seconds and shows each rule's last evaluation time.

## Background evaluation

The supplied Compose configuration defaults `ALERT_WORKER_ENABLED` to `true`. Local Python runs default to manual evaluation unless that environment variable is set to `true`. The UI shows the configured mode. Changes to the flag require restarting the backend.

Each process polls every 30 seconds, evaluating rules not checked in the preceding 60 seconds. Typical latency is about one minute, not an exact delivery deadline. Each pass visits up to 100 due businesses, advancing a cursor so a failing business does not permanently starve later businesses. Suspended businesses are skipped. Errors are logged and retried on a later pass; stale last-evaluation timestamps remain visible. There are no external delivery jobs or messages.

All evaluations, rule edits and acknowledgements use the same tenant row lock as stock/POS writes. A worker rechecks which rules are due after taking the lock. A partial unique index additionally permits only one open/acknowledged episode per rule/entity. Matching writes are batched. The worker stops before the connection pool closes during application shutdown. These mechanisms are implemented; real PostgreSQL multi-process contention/load still requires production acceptance.

## API and upgrade

New API prefix: `/api/v1/tenants/{tenant}/alert-center`. The previous `/inventory-alerts` endpoint used by the batch dashboard is preserved unchanged.

Back up PostgreSQL and preserve `.env`, then rebuild backend/frontend. Additive migration **018_inventory_alerts.sql** creates rule/event tables and indexes. Migrations 001–017 and the existing PostgreSQL network setup remain unchanged. No new dependency is required.

This completes inventory-focused in-app rules and lifecycle handling, not the entire alerts specification. Email/SMS/WhatsApp/push, Urdu voice, quiet hours, escalations, financial/security/predictive rules and external delivery retries remain missing. Offline sync, multi-store, partial returns, loyalty, subscriptions and other CHECKLIST.md gaps also remain implementation work.
