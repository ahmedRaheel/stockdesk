-- Business operations: store scopes, warehouse movements, serials, append-only GL and wallets.
CREATE TABLE store_locations (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), code text NOT NULL,
 name text NOT NULL, kind text NOT NULL CHECK(kind IN ('store','warehouse')),
 address text NOT NULL DEFAULT '', active boolean NOT NULL DEFAULT true,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,code)
);
CREATE TABLE warehouse_balances (
 tenant text NOT NULL, location text NOT NULL, product text NOT NULL,
 quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK(quantity>=0),
 PRIMARY KEY(tenant,location,product),
 FOREIGN KEY(tenant,location) REFERENCES store_locations(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE warehouse_transfer_headers (
 id text PRIMARY KEY, tenant text NOT NULL, request text NOT NULL,
 source text NOT NULL, destination text NOT NULL, actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,request),
 CHECK(source<>destination),
 FOREIGN KEY(tenant,source) REFERENCES store_locations(tenant,id),
 FOREIGN KEY(tenant,destination) REFERENCES store_locations(tenant,id)
);
CREATE TABLE warehouse_transfer_lines (
 transfer text NOT NULL, tenant text NOT NULL, product text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0), PRIMARY KEY(transfer,product),
 FOREIGN KEY(tenant,transfer) REFERENCES warehouse_transfer_headers(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE product_serials (
 id text PRIMARY KEY,tenant text NOT NULL,product text NOT NULL,serial_number text NOT NULL,
 location text, status text NOT NULL DEFAULT 'available' CHECK(status IN ('available','sold','returned','scrapped')),
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,serial_number),
 UNIQUE(tenant,id), FOREIGN KEY(tenant,product) REFERENCES products(tenant,id),
 FOREIGN KEY(tenant,location) REFERENCES store_locations(tenant,id)
);
CREATE TABLE gl_accounts (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), code text NOT NULL,
 name text NOT NULL, kind text NOT NULL CHECK(kind IN ('asset','liability','equity','income','expense')),
 active boolean NOT NULL DEFAULT true, UNIQUE(tenant,id), UNIQUE(tenant,code)
);
CREATE TABLE gl_journals (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),request text NOT NULL,
 memo text NOT NULL, reference text NOT NULL DEFAULT '', actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,request)
);
CREATE TABLE gl_entries (
 journal text NOT NULL,tenant text NOT NULL,account text NOT NULL,
 debit bigint NOT NULL DEFAULT 0 CHECK(debit>=0), credit bigint NOT NULL DEFAULT 0 CHECK(credit>=0),
 CHECK((debit>0 AND credit=0) OR (credit>0 AND debit=0)),
 FOREIGN KEY(tenant,journal) REFERENCES gl_journals(tenant,id),
 FOREIGN KEY(tenant,account) REFERENCES gl_accounts(tenant,id)
);
CREATE INDEX gl_entries_by_account ON gl_entries(tenant,account);
CREATE FUNCTION gl_posted_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Posted journal entries cannot be changed; post a reversing journal'; END $$;
CREATE TRIGGER gl_journals_immutable BEFORE UPDATE OR DELETE ON gl_journals FOR EACH ROW EXECUTE FUNCTION gl_posted_immutable();
CREATE TRIGGER gl_entries_immutable BEFORE UPDATE OR DELETE ON gl_entries FOR EACH ROW EXECUTE FUNCTION gl_posted_immutable();
CREATE TABLE customer_wallet_entries (
 id text PRIMARY KEY,tenant text NOT NULL,customer text NOT NULL,request text NOT NULL,
 amount bigint NOT NULL CHECK(amount<>0),reason text NOT NULL,actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,request),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id)
);
CREATE INDEX wallet_history ON customer_wallet_entries(tenant,customer,created,id);
CREATE TRIGGER wallet_entries_immutable BEFORE UPDATE OR DELETE ON customer_wallet_entries FOR EACH ROW EXECUTE FUNCTION gl_posted_immutable();
CREATE TABLE subscription_plans (
 id text PRIMARY KEY,code text NOT NULL UNIQUE,name text NOT NULL,
 monthly_price bigint NOT NULL CHECK(monthly_price>=0),currency text NOT NULL DEFAULT 'PKR',
 max_stores integer NOT NULL CHECK(max_stores>=1),active boolean NOT NULL DEFAULT true
);
CREATE TABLE tenant_subscriptions (
 tenant text PRIMARY KEY REFERENCES tenants(id), plan text NOT NULL REFERENCES subscription_plans(id),
 status text NOT NULL CHECK(status IN ('trial','active','past_due','cancelled')),
 starts timestamptz NOT NULL, ends timestamptz NOT NULL,
 CHECK(ends>starts)
);
CREATE TABLE tenant_usage_events (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),request text NOT NULL,
 metric text NOT NULL CHECK(metric IN ('sale','api_call','storage_bytes','invoice')),
 units bigint NOT NULL CHECK(units>0), recorded timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request,metric)
);
CREATE INDEX tenant_usage_report ON tenant_usage_events(tenant,metric,recorded);
CREATE TABLE offline_devices (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),name text NOT NULL,
 user_id text NOT NULL REFERENCES users(id),active boolean NOT NULL DEFAULT true,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id)
);
CREATE TABLE offline_operations (
 tenant text NOT NULL,device text NOT NULL,operation_id text NOT NULL,
 payload_hash char(64) NOT NULL,status text NOT NULL CHECK(status IN ('accepted','rejected')),
 result jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant,device,operation_id),
 FOREIGN KEY(tenant,device) REFERENCES offline_devices(tenant,id)
);
CREATE TABLE fiscal_submissions (
 id text PRIMARY KEY,tenant text NOT NULL,sale text NOT NULL,
 provider text NOT NULL DEFAULT 'FBR',status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','submitted','accepted','rejected')),
 external_reference text,request_payload jsonb, response_payload jsonb, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,sale), FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
