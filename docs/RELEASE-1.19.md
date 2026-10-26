# StockDesk 1.19 — in-app inventory alert escalation

An inventory rule can now raise an unacknowledged open alert from information or warning to critical after a configured number of minutes. Set “Escalate to critical after minutes” from 1 to 10,080 (seven days), or leave it blank to disable. Critical rules cannot configure escalation. Existing rules default to no escalation.

The timer starts when an alert episode is first opened. Escalation happens on the first successful evaluation at or after the deadline, not on an exact-time alarm. With the alert worker enabled, rules are normally evaluated about once per minute; otherwise use Evaluate alerts now. Processing delays may postpone escalation.

Cleared conditions resolve before escalation, and acknowledged alerts never escalate. An episode escalates only once: repeated evaluations preserve its timestamp. The alert retains its prior severity, threshold and escalation time after acknowledgement or resolution. Rule edits close existing episodes as before; a recurring condition gets a new episode and timer. No notification is sent outside StockDesk, and this release does not add recipient chains or external delivery.

The inbox includes “Escalated alerts only”, combined with its status filter. Choose All or Resolved to inspect historical escalations. Existing alert permissions, tenant locking, CSRF checks, audit records and background-worker suspension checks remain in effect. Escalation adds an audit entry containing the rule, number of affected alerts and configured threshold.

## API

Rule create/update accepts nullable `escalate_after_minutes`, a strict integer from 1 through 10,080; it is invalid with severity `critical`. Alert rows add `escalated_at`, `escalated_from`, and `escalation_minutes`. The inbox accepts `escalated_only=true`; evaluation responses add an `escalated` count. These changes preserve existing defaults.

## Upgrade

Back up PostgreSQL and preserve `.env`, then deploy backend and frontend together using README commands. Migration **024_alert_escalation.sql** adds optional escalation fields and constraints. Migrations 001–023 remain unchanged. No dependencies were added, and the existing external `postgres` / `chatbot-network` arrangement and EC2 HTTP UUID fallback remain included.

This completes timed in-app severity escalation. Quiet hours, external delivery, recipient escalation chains and other enterprise gaps remain in CHECKLIST.md. Real PostgreSQL multiprocess/load, live EC2/Docker and hardware/provider acceptance remain unverified.
