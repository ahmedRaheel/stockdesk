ALTER TABLE tenants ADD COLUMN z_report_seq bigint NOT NULL DEFAULT 0;
CREATE TABLE till_return_events (
 id text PRIMARY KEY,tenant text NOT NULL,sale text NOT NULL,till_session text,
 source text NOT NULL,total bigint NOT NULL CHECK(total>=0),tax bigint NOT NULL CHECK(tax>=0),
 actor text NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,source),FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id),
 FOREIGN KEY(tenant,till_session) REFERENCES till_sessions(tenant,id)
);
CREATE TABLE till_z_reports (
 tenant text NOT NULL,session text NOT NULL,number bigint NOT NULL,
 snapshot jsonb NOT NULL,digest text NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant,session),UNIQUE(tenant,number),
 FOREIGN KEY(tenant,session) REFERENCES till_sessions(tenant,id)
);
CREATE FUNCTION reject_till_report_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Till report evidence is immutable' USING ERRCODE='23514'; END $$;
CREATE TRIGGER till_report_immutable BEFORE UPDATE OR DELETE ON till_z_reports FOR EACH ROW EXECUTE FUNCTION reject_till_report_edit();
CREATE TRIGGER till_return_event_immutable BEFORE UPDATE OR DELETE ON till_return_events FOR EACH ROW EXECUTE FUNCTION reject_till_report_edit();
