CREATE TABLE membership_plans (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),code text NOT NULL,name text NOT NULL,
 duration_days integer NOT NULL CHECK(duration_days BETWEEN 1 AND 730),benefits text NOT NULL DEFAULT '',
 active boolean NOT NULL DEFAULT true,version integer NOT NULL DEFAULT 1,
 UNIQUE(tenant,id),UNIQUE(tenant,code)
);
CREATE TABLE membership_sequences (tenant text PRIMARY KEY REFERENCES tenants(id),last_number bigint NOT NULL);
CREATE TABLE customer_memberships (
 id text PRIMARY KEY,tenant text NOT NULL,customer text NOT NULL,plan text NOT NULL,number text NOT NULL,
 plan_snapshot jsonb NOT NULL,valid_from date NOT NULL,valid_until date NOT NULL,
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled')),
 version integer NOT NULL DEFAULT 1,created timestamptz NOT NULL DEFAULT now(),updated timestamptz NOT NULL DEFAULT now(),
 CHECK(valid_until>=valid_from),UNIQUE(tenant,id),UNIQUE(tenant,number),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id),FOREIGN KEY(tenant,plan) REFERENCES membership_plans(tenant,id)
);
CREATE INDEX memberships_customer_dates ON customer_memberships(tenant,customer,status,valid_from,valid_until);
CREATE TABLE membership_events (
 id text PRIMARY KEY,tenant text NOT NULL,membership text NOT NULL,request text NOT NULL,signature text NOT NULL,
 actor text NOT NULL,kind text NOT NULL CHECK(kind IN ('enrolled','renewed','cancelled')),
 note text NOT NULL,details jsonb NOT NULL,version integer NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request),UNIQUE(tenant,membership,version),
 FOREIGN KEY(tenant,membership) REFERENCES customer_memberships(tenant,id)
);
CREATE FUNCTION reject_membership_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Membership history is immutable; append an action'; END $$;
CREATE TRIGGER membership_history_immutable BEFORE UPDATE OR DELETE ON membership_events FOR EACH ROW EXECUTE FUNCTION reject_membership_history_change();
