-- Per-serial immutable transition history; no retroactive modifications.
CREATE TABLE product_serial_events (
 id text PRIMARY KEY, tenant text NOT NULL, request text NOT NULL,
 serial_id text NOT NULL, status text NOT NULL CHECK(status IN ('sold','returned','scrapped')),
 sale text, notes text NOT NULL DEFAULT '', actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request),
 FOREIGN KEY(tenant,serial_id) REFERENCES product_serials(tenant,id),
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
CREATE INDEX serial_events_by_serial ON product_serial_events(tenant,serial_id,created);
CREATE TRIGGER serial_events_immutable BEFORE UPDATE OR DELETE ON product_serial_events
 FOR EACH ROW EXECUTE FUNCTION gl_posted_immutable();
