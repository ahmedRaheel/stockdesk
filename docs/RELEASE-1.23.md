# StockDesk 1.23 — combined promotions

Enable **Allow combining with other offers** on each eligible promotion. In POS, enter two to five distinct comma-separated codes. Existing offers default to not stackable. Automatic selection still chooses one best offer; manual discounts cannot be combined with promotional codes.

Product-specific offers apply first, then fixed discounts, then percentages; alphabetical code resolves ties. Percentages apply sequentially to the remaining value. Product discounts stay on their intended lines and cannot reduce a line below zero. A zero-contribution offer rejects the combination, so no redemption is wasted. Minimum spends evaluate against the original cart. Each offer retains its own date, customer and usage restrictions.

Preview and checkout share the same calculation, tax rounding and frozen line allocations. Checkout records each redemption atomically and requires a fresh quote. Retries do not spend another redemption. Held bills preserve the codes. POS, receipt and PDF show the combined total and each applied offer.

Returns use the original combined line discounts. Cross-product BOGO pairs remain linked after stacking; overlapping pairs form one return group, while unrelated pairs remain independent. Existing return rules and approvals still apply.

Migration 029 adds the stackable flag and allows one redemption row per offer per sale. Existing migrations and deployment configuration are unchanged. Use the existing external PostgreSQL deployment; no new database container or dependency is required.

This release completes explicit promotion stacking, not the whole enterprise checklist. The remaining modules and agreed exclusions remain recorded in CHECKLIST.md and COMPLETION-ROADMAP.md. No live EC2 deployment or statutory certification is claimed.
