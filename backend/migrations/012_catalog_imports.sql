CREATE TABLE catalog_imports (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), request text NOT NULL,
 signature text NOT NULL, product_ids jsonb NOT NULL, actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,request)
);
