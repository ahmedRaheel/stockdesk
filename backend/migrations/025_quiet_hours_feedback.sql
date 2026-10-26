ALTER TABLE inventory_alert_rules ADD COLUMN quiet_start integer;
ALTER TABLE inventory_alert_rules ADD COLUMN quiet_end integer;
ALTER TABLE inventory_alert_rules ADD CONSTRAINT quiet_window CHECK((quiet_start IS NULL AND quiet_end IS NULL) OR (quiet_start IS NOT NULL AND quiet_end IS NOT NULL AND quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 1 AND 1440 AND quiet_start<>quiet_end));
CREATE TABLE customer_feedback (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), request text NOT NULL, signature text NOT NULL,
 sale text, rating integer NOT NULL CHECK(rating BETWEEN 1 AND 5), comment text NOT NULL,
 status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')), resolution text NOT NULL DEFAULT '',
 version integer NOT NULL DEFAULT 1, created_by text NOT NULL, updated_by text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(), updated timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id), UNIQUE(tenant,request), FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
CREATE INDEX feedback_inbox ON customer_feedback(tenant,status,created DESC);
