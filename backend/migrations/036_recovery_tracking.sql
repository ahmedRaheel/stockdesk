CREATE TABLE recovery_cases (
 id text PRIMARY KEY, tenant text NOT NULL, receivable text NOT NULL,
 assigned_to text NOT NULL REFERENCES users(id), next_follow_up timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed','cancelled')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created_by text NOT NULL REFERENCES users(id), created timestamptz NOT NULL DEFAULT now(),
 updated timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id),
 FOREIGN KEY(tenant,receivable) REFERENCES receivables(tenant,id)
);
CREATE UNIQUE INDEX recovery_one_open_invoice ON recovery_cases(tenant,receivable) WHERE status='open';
CREATE INDEX recovery_due ON recovery_cases(tenant,status,next_follow_up,id);
CREATE INDEX recovery_agent ON recovery_cases(tenant,assigned_to,status,next_follow_up);
CREATE TABLE recovery_events (
 id text PRIMARY KEY, tenant text NOT NULL, case_id text NOT NULL,
 request text NOT NULL, signature text NOT NULL, actor text NOT NULL REFERENCES users(id),
 kind text NOT NULL CHECK(kind IN ('created','updated','contacted','no_answer','visited','disputed','promise','note')),
 note text NOT NULL CHECK(length(note) BETWEEN 1 AND 2000),
 details jsonb NOT NULL, version integer NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request), FOREIGN KEY(tenant,case_id) REFERENCES recovery_cases(tenant,id)
);
CREATE INDEX recovery_history ON recovery_events(tenant,case_id,created DESC,id);
CREATE FUNCTION reject_recovery_event_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Recovery history is immutable; append a correction'; END $$;
CREATE TRIGGER recovery_event_immutable BEFORE UPDATE OR DELETE ON recovery_events FOR EACH ROW EXECUTE FUNCTION reject_recovery_event_change();

CREATE INDEX customer_ledger_receivable ON customer_ledger(tenant,receivable);
