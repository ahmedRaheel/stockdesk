CREATE TABLE customer_campaigns (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), name text NOT NULL,
 message text NOT NULL, audience text NOT NULL CHECK(audience IN ('all','members')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
 version integer NOT NULL DEFAULT 1, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id)
);
CREATE TABLE campaign_optouts (
 tenant text NOT NULL, customer text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant,customer), FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id)
);
CREATE TABLE campaign_recipients (
 tenant text NOT NULL, campaign text NOT NULL, customer text NOT NULL,
 name text NOT NULL, phone text NOT NULL,
 outcome text NOT NULL DEFAULT 'pending' CHECK(outcome IN ('pending','contacted','interested','not_interested','no_answer','opted_out','skipped')),
 version integer NOT NULL DEFAULT 1,
 PRIMARY KEY(tenant,campaign,customer),
 FOREIGN KEY(tenant,campaign) REFERENCES customer_campaigns(tenant,id),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id)
);
CREATE TABLE campaign_events (
 id text PRIMARY KEY, tenant text NOT NULL, campaign text NOT NULL, customer text,
 request text NOT NULL, signature text NOT NULL, actor text NOT NULL, kind text NOT NULL,
 note text NOT NULL, details jsonb NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request), FOREIGN KEY(tenant,campaign) REFERENCES customer_campaigns(tenant,id)
);
CREATE INDEX campaign_events_order ON campaign_events(tenant,campaign,created,id);
CREATE FUNCTION reject_campaign_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Campaign history is immutable; append an action'; END $$;
CREATE TRIGGER campaign_history_immutable BEFORE UPDATE OR DELETE ON campaign_events FOR EACH ROW EXECUTE FUNCTION reject_campaign_history_change();
