-- StockDesk 1.42: public storefront, requests, and idempotent import batches.
-- Public orders are NOT paid sales and never bypass the POS stock ledger.
CREATE TABLE storefronts (
 tenant text PRIMARY KEY REFERENCES tenants(id),
 slug text NOT NULL UNIQUE CHECK(slug ~ '^[a-z0-9][a-z0-9-]{2,47}$'),
 title text NOT NULL DEFAULT '',
 description text NOT NULL DEFAULT '',
 published boolean NOT NULL DEFAULT false,
 updated timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE storefront_listings (
 tenant text NOT NULL,product text NOT NULL,published boolean NOT NULL DEFAULT false,
 featured boolean NOT NULL DEFAULT false,sort_order integer NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant,product),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE storefront_orders (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),
 request_id text NOT NULL,signature text NOT NULL,
 customer_name text NOT NULL,customer_email text NOT NULL DEFAULT '',customer_phone text NOT NULL,
 notes text NOT NULL DEFAULT '',
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','fulfilled')),
 total bigint NOT NULL CHECK(total>=0),currency text NOT NULL,
 ip_digest text NOT NULL DEFAULT '',sale_id text,
 handled_by text REFERENCES users(id),created timestamptz NOT NULL DEFAULT now(),updated timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request_id), UNIQUE(tenant,id),
 FOREIGN KEY(tenant,sale_id) REFERENCES sales(tenant,id)
);
CREATE INDEX storefront_orders_recent ON storefront_orders(tenant,created DESC);
CREATE INDEX storefront_orders_ip_rate ON storefront_orders(tenant,ip_digest,created DESC);
CREATE TABLE storefront_order_lines (
 tenant text NOT NULL,order_id text NOT NULL,product text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0),
 unit_price bigint NOT NULL CHECK(unit_price>=0),name text NOT NULL,
 PRIMARY KEY(tenant,order_id,product),
 FOREIGN KEY(tenant,order_id) REFERENCES storefront_orders(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE migration_batches (
 tenant text NOT NULL REFERENCES tenants(id),request_id text NOT NULL,
 signature text NOT NULL,summary jsonb NOT NULL,actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant,request_id)
);
