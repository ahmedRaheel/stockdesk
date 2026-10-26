# StockDesk 1.20 — quiet hours and customer feedback

## Alert quiet hours

Inventory rules accept optional daily quiet start/end times in Asia/Karachi. Same-day and overnight windows are supported; start is inclusive and end exclusive. End 00:00 means midnight at the end of the day (API 1440). Start 00:00/end 00:00 therefore means all day; clear both fields to disable quiet hours. Other equal endpoints and half-specified windows are invalid.

During quiet hours, evaluation defers new alert episodes and severity escalation, including critical alerts. Existing alerts remain visible, their details update, acknowledgement still works, and cleared conditions resolve. When quiet hours end, only currently matching conditions open new episodes; transient conditions that cleared are not replayed. Existing overdue escalation occurs on the next eligible evaluation; its timer is not reset or paused. Manual Evaluate respects quiet hours too. API evaluation responses add a `deferred` count of matching new entities skipped on that pass, not a durable pending queue. Rule edits retain the existing close-old-episode behavior.

Rule bodies add nullable `quiet_start` (0–1439) and `quiet_end` (1–1440). Both default null. Worker timing remains approximate and requires ALERT_WORKER_ENABLED; manual mode remains supported.

## Customer feedback

Owners and Managers have a Customer feedback screen; custom roles may receive the new `feedback` permission. Cashiers and stock managers do not receive it by default. Staff record a 1–5 rating and comment, optionally linking an invoice number from the same business. This is internal capture of feedback received from customers, not a public review portal or an authenticated customer submission channel.

Submissions preserve the original rating/comment. Retrying the same request and data by the same actor returns the existing entry; conflicting reuse is rejected. A note and current version are required to resolve or reopen an entry. Original feedback remains unchanged; resolution history is available in the audit log. The inbox filters open/resolved/all records and shows all-time tenant totals, open count and average rating. The aggregate is descriptive; it is not verified customer satisfaction research.

API prefix: `/api/v1/tenants/{tenant}/feedback`.

- GET: `status=all|open|resolved`, bounded `limit`/`offset`; returns items, filtered total and tenant-wide summary.
- POST: `request`, `rating`, `comment`, optional `invoice_number`.
- PUT `/{id}`: `version`, `status=open|resolved`, `note`.

Reads/writes require `feedback`, writes require CSRF, and updates use the existing tenant lock. Invoice references are resolved within the tenant. Creating/editing feedback ratings, deleting entries, customer portals, campaigns and notifications are not added.

## Upgrade

Back up PostgreSQL, preserve `.env`, and deploy backend/frontend together using README instructions. Migration **025_quiet_hours_feedback.sql** adds quiet-hour constraints and the feedback table. Migrations 001–024 are unchanged. Existing external PostgreSQL/network settings are preserved; no dependencies added.

This release completes two bounded checklist features. The enterprise checklist is not fully complete. See CHECKLIST.md and COMPLETION-ROADMAP.md for remaining implementation and acceptance work.
