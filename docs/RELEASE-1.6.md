# StockDesk 1.6 — custom business roles and searchable audit history

This release adds tenant-level configurable authorization. It does not claim completion of the enterprise checklist; CHECKLIST.md records the remaining modules.

## Create and assign roles

The business Owner or platform administrator opens **Custom roles**. Choose a name, optional Urdu display name, and capabilities. The capability catalogue and staff/role dropdowns come from authenticated database-backed APIs. Roles apply only within the selected business. A role may have up to 13 supported capability groups; the business supports at most 100 custom roles.

Create staff accounts through **Team & roles** first, then assign their custom role. A custom role replaces the member's effective built-in permissions; it is not an additive grant. An inactive member remains inactive after assignment. Assign a built-in role through Team & roles to explicitly clear the custom assignment. Existing built-in memberships keep their previous operating access.

The Owner membership cannot be overridden. Built-in names are reserved. Ownership, team management and role administration cannot be granted through the custom-role catalogue. Platform administrators retain their existing platform-level authority.

## Permission rules

Every role requires catalog read access. Capabilities cover sales/receipts, whole-sale returns, customer credit, credit approval, cost/reports, catalog writes, purchasing/stock, independent stock-count approval, forecasts, supplier finance, business settings/reference data and audit reading. These are feature groups, not per-field, per-price-limit or per-action policies within each feature.

The UI selects prerequisites and the server enforces them independently. Product writes, stock operations, forecasting, finance and audit require cost access because those workflows can expose financial values. Returns require sales access; credit approval requires customer credit access; stock-count approval requires stock and cost access. A cashier role without cost permission receives redacted product and receipt costs in both legacy and versioned APIs. Audit access deliberately grants access to financial details in historical events; do not assign it to frontline staff who must not see those values.

Disabling a custom role denies its members on the next tenant API request. Editing permissions affects existing sessions on their next request; no re-login is needed. Already displayed browser data is not remotely erased. Role writes and business writes use the same tenant lock. Stale role edits are rejected through a version field. A role cannot be deleted to erase its assignment/audit history; disable it instead.

Stock-count approval now uses its explicit capability. The existing maker/checker rule still requires a different user from the count creator. Credit approval retains its existing rules.

## Audit history

**Activity log** is independently gated by audit permission. Search actor, action or details, optionally filter inclusive UTC dates, and page through results. The API caps pages at 100; the UI uses 50. Expand details and export the current page to CSV. Formula-looking export cells are neutralized. Export is not a scheduled or whole-database archive.

Audit events remain append-only through the application APIs. This is not cryptographically tamper-evident storage against a database administrator, a retention policy, or a full compliance audit system. Existing events may be English. The UI includes English/Urdu labels and RTL.

## Upgrade and limits

Back up PostgreSQL, preserve `.env`, replace source, then rebuild backend/frontend as described in README. Migration 013 is additive; migrations 001–012 are unchanged. Existing members have no custom role until assigned. Default Compose still uses your existing PostgreSQL container/network.

This does not yet implement regional/store scopes, multiple concurrent roles per member, explicit denies, time-limited grants, transaction limits, delegated team administration, supervisor PIN/biometric, SSO/MFA or support impersonation. Offline sync, multi-store transfers, promotions, external integrations and the other CHECKLIST.md omissions still require implementation.
