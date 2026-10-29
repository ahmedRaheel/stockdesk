# StockDesk 1.27 — financial alerts and alert center UI

## Completed

- Overdue customer invoice alerts use current positive receivable ledger balances after recoveries and credits. Requires alerts + credit permissions. Invoice due dates are used, not individual installment dates.
- Overdue supplier bill alerts use posted payable balances after payments, returns and refunds. Requires alerts + finance permissions.
- Closed-till cash discrepancy alerts cover both shortages and surpluses within a 1–365 day lookback. Requires alerts + finance permissions. Signed variance and expected/count amounts are shown.
- Financial rules accept a minimum amount in major currency units, with two decimal places. Zero grace days starts the day after the invoice due date; zero minimum still excludes zero balances.
- All rule lists, alert counts/details, edits, acknowledgement and manual evaluation enforce the underlying permission. Background evaluation covers all active rules. Quiet hours, timed escalation and episode resolution remain supported.
- Redesigned alert center: Inbox/Rules navigation, status filters, severity badges, readable evidence cards, inline acknowledgement, clear empty states, separate rule editor and optional quiet-hour/escalation settings. Mobile layout and Urdu translations are included.

## Behavior and deployment

Acknowledgement records follow-up only. It does not change payments, inventory or accounting. Cash episodes resolve when outside their lookback window; this does not mean the discrepancy was corrected. Each rule is bounded to 5,000 matches. Narrow scope, increase a threshold or shorten a lookback if exceeded. No external message is sent.

Rebuild backend and frontend Docker images. Startup applies migration 033 to the existing PostgreSQL database. Prior migrations and external PostgreSQL Docker settings are unchanged. No new runtime dependency is required.

Security/predictive alerts, recipient escalation chains, push/retry delivery, offline sales, warehouses, advanced finance and other checklist gaps remain open. This release is not a claim of full completion or production deployment.
