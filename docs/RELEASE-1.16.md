# StockDesk 1.16 — cross-product BOGO

Create an explicit-code offer such as “buy 2 teas, get 1 milk free” in Promotions. Select the qualifying product and reward product separately, then set buy/free counts. The reward must already be in the cart; stock is never silently added. Additional reward units stay paid. Discounts apply only to eligible reward units and use the existing tax calculation, schedule, minimum-spend, maximum-discount and global usage controls. A monetary discount cap can reduce the discount below the full price of the eligible reward units.

## API

Promotion create/update accepts `kind: "cross_bogo"`, `value: 0`, `reward_product`, `buy_quantity`, `free_quantity`, and exactly two distinct `components`, each with quantity 1. The reward ID must identify one component; the other is the qualifying product. Both must use whole-unit units. Component order does not determine the roles. Other promotion kinds reject a reward ID. Inactive component products prevent activation, but existing offers can still be disabled.

Checkout freezes qualifying/reward IDs, quantities, eligible reward units and the return policy in its promotion snapshot. Receipt responses include `sale.return_pair_products` where applicable. Live promotion edits cannot rewrite the original sale's return policy.

## Returns

To adjust either promotional product, return **all remaining quantities of both products together**, including any extra paid reward or qualifying units. The adjustment screen provides “Select all promotional items”; the API enforces the policy. Unrelated products can be returned independently. Original-price credit, replacement-item payment/refund, cash change, tax, stock disposition and audit snapshots continue through the existing adjustment workflow. The paired-return policy appears on receipts and PDFs, including after unrelated-item adjustments.

Partial-pair repricing, automatic offers, stacking, per-customer limits, partial khata adjustments and payment-provider settlement remain outside this release. See CHECKLIST.md for other outstanding work.

## Upgrade

Back up PostgreSQL and preserve `.env`. Deploy backend and frontend together using the existing README upgrade steps. New migration **021_cross_product_bogo.sql** adds the promotion kind and tenant-scoped reward-product reference; migrations 001–020 are unchanged. The default external `postgres` container on `chatbot-network` is preserved. The HTTP request-ID fallback from 1.15.1 remains included. No dependencies were added.
