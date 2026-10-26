# StockDesk 1.18 — automatic offer selection

Managers can mark an offer “Available for automatic selection”. Cashiers enable “Automatically select an offer” in POS. The server evaluates eligible automatic offers against the current cart and selected customer, then chooses the lowest final bill including tax. Exact total ties use ascending promotion code, then ID. Only one offer applies; codes and manual discounts cannot be combined with automatic mode.

All supported offer types participate: fixed, percentage, same-product BOGO, cross-product BOGO and bundles. Existing schedules, minimum spend, caps and customer/global redemption limits apply. Cross-product free units must already be in the cart. Ineligible offers are skipped, including customer-limited offers without an eligible registered customer. With no eligible offer, the normal undiscounted quote is returned. Existing explicit-code behavior remains available.

Quote results show the winning offer. Checkout recalculates under the existing tenant write lock and rejects an outdated quote when the winner or resulting bill changes. A quote does not reserve stock or usage. Successful sales freeze the selected offer, record one redemption, and retain existing receipt, return-policy and idempotency behavior. Returns do not replenish promotion limits. Held bills preserve the automatic-mode choice and are requoted on resume.

## API and bounds

Promotion create/update adds `automatic` (strict boolean, default false). A business may have at most 100 active automatic offers; disable one before activating another. Evaluation is bounded and fails explicitly if data inserted outside the API exceeds this bound; it never silently truncates candidate selection.

Quote, checkout and held-bill bodies accept `auto_promotion` (strict boolean, default false). Auto quotes return `auto_promotion: true`, including when no offer qualifies. The winning promotion snapshot includes `automatic: true`. Automatic checkout always requires a current quote token, including in manual tax mode and when no offer qualifies. Existing clients default to explicit selection.

## Upgrade

Back up PostgreSQL, preserve `.env`, and deploy backend/frontend together using README commands. Migration **023_automatic_promotions.sql** adds the default-false flag and an index. Migrations 001–022 are unchanged. Existing promotions are not enrolled automatically. The default external `postgres` / `chatbot-network` arrangement and HTTP UUID fallback remain. No dependencies added.

This release completes bounded automatic single-offer selection. Stacking, independent discount approvals and other enterprise gaps remain listed in CHECKLIST.md. Live EC2/Docker deployment, hardware and real PostgreSQL multiprocess load acceptance remain unverified.
