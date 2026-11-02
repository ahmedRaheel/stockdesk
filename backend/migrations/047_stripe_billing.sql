-- Stripe billing is opt-in. Existing manually assigned subscriptions remain intact.
ALTER TABLE subscription_plans ADD COLUMN stripe_price_id text UNIQUE;
CREATE TABLE stripe_checkout_sessions (
 session_id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id),
 plan text NOT NULL REFERENCES subscription_plans(id),request text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant,request)
);
CREATE TABLE stripe_subscription_links (
 subscription_id text PRIMARY KEY, tenant text NOT NULL UNIQUE REFERENCES tenants(id),
 plan text NOT NULL REFERENCES subscription_plans(id),
 created timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE stripe_webhook_events (
 event_id text PRIMARY KEY, kind text NOT NULL, received timestamptz NOT NULL DEFAULT now()
);
