CREATE TABLE suppliers (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), name text NOT NULL,
 contact text NOT NULL DEFAULT '', lead_days integer NOT NULL CHECK (lead_days BETWEEN 0 AND 365),
 created timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant,id), UNIQUE (tenant,name)
);
CREATE TABLE purchase_orders (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), supplier text NOT NULL,
 request text NOT NULL, signature text NOT NULL, reference text NOT NULL DEFAULT '',
 status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','partial','received','cancelled')),
 created timestamptz NOT NULL DEFAULT now(), actor text NOT NULL,
 UNIQUE (tenant,id), UNIQUE (tenant,request), FOREIGN KEY (tenant,supplier) REFERENCES suppliers(tenant,id)
);
CREATE TABLE purchase_lines (
 tenant text NOT NULL, purchase text NOT NULL, product text NOT NULL,
 quantity bigint NOT NULL CHECK (quantity>0), received bigint NOT NULL DEFAULT 0 CHECK (received>=0 AND received<=quantity),
 unit_cost bigint NOT NULL CHECK (unit_cost>=0), PRIMARY KEY (tenant,purchase,product),
 FOREIGN KEY (tenant,purchase) REFERENCES purchase_orders(tenant,id),
 FOREIGN KEY (tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE purchase_receipts (
 id text PRIMARY KEY, tenant text NOT NULL, purchase text NOT NULL, request text NOT NULL,
 signature text NOT NULL, actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE (tenant,request), FOREIGN KEY (tenant,purchase) REFERENCES purchase_orders(tenant,id)
);
CREATE INDEX purchase_tenant_created ON purchase_orders(tenant,created DESC,id);
CREATE INDEX products_tenant_name_id ON products(tenant,name,id);
CREATE INDEX sale_items_tenant_product ON sale_items(tenant,product);
