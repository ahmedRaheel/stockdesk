CREATE TABLE inventory_alert_rules (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),name text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('low_stock','stock_out','expiry')),
 product text,threshold numeric(18,3) CHECK(threshold>=0),expiry_days integer NOT NULL DEFAULT 30 CHECK(expiry_days BETWEEN 0 AND 365),
 severity text NOT NULL CHECK(severity IN ('info','warning','critical')),
 active boolean NOT NULL DEFAULT true,version integer NOT NULL DEFAULT 1,last_evaluated timestamptz,
 created timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant,id),UNIQUE(tenant,name),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE inventory_alerts (
 id text PRIMARY KEY,tenant text NOT NULL,rule text NOT NULL,entity text NOT NULL,
 rule_name text NOT NULL,kind text NOT NULL,severity text NOT NULL,details jsonb NOT NULL,
 status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','resolved')),
 opened timestamptz NOT NULL DEFAULT now(),last_seen timestamptz NOT NULL DEFAULT now(),
 acknowledged timestamptz,acknowledged_by text,acknowledgement_note text,
 resolved timestamptz,resolution text,
 UNIQUE(tenant,id),FOREIGN KEY(tenant,rule) REFERENCES inventory_alert_rules(tenant,id)
);
CREATE UNIQUE INDEX inventory_alert_live ON inventory_alerts(tenant,rule,entity) WHERE status IN ('open','acknowledged');
CREATE INDEX inventory_alert_inbox ON inventory_alerts(tenant,status,opened DESC);
