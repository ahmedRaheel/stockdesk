CREATE TABLE report_schedules (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), name text NOT NULL,
 owner_id text NOT NULL REFERENCES users(id), definition jsonb NOT NULL, last_signature text NOT NULL,
 frequency text NOT NULL CHECK(frequency IN ('daily','weekly')), weekday integer NOT NULL CHECK(weekday BETWEEN 0 AND 6),
 hour integer NOT NULL CHECK(hour BETWEEN 0 AND 23), minute integer NOT NULL CHECK(minute BETWEEN 0 AND 59),
 active boolean NOT NULL DEFAULT true, next_run timestamptz NOT NULL, retry_after timestamptz,
 version integer NOT NULL DEFAULT 1, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id)
);
CREATE INDEX report_schedules_due ON report_schedules(active,next_run);
CREATE TABLE report_runs (
 id text PRIMARY KEY, tenant text NOT NULL, schedule text NOT NULL, scheduled_for timestamptz NOT NULL,
 definition jsonb NOT NULL, schedule_name text NOT NULL, owner_email text NOT NULL, status text NOT NULL CHECK(status IN ('retrying','succeeded','failed','cancelled')),
 attempts integer NOT NULL CHECK(attempts BETWEEN 1 AND 3), result jsonb, error text NOT NULL DEFAULT '',
 created timestamptz NOT NULL DEFAULT now(), finished timestamptz,
 UNIQUE(tenant,schedule,scheduled_for), FOREIGN KEY(tenant,schedule) REFERENCES report_schedules(tenant,id)
);
CREATE INDEX report_runs_inbox ON report_runs(tenant,created DESC,id);
CREATE FUNCTION protect_successful_report_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF OLD.status='succeeded' THEN RAISE EXCEPTION 'Successful report snapshots cannot be changed'; END IF; RETURN NEW; END $$;
CREATE TRIGGER report_run_snapshot_frozen BEFORE UPDATE ON report_runs FOR EACH ROW EXECUTE FUNCTION protect_successful_report_run();
