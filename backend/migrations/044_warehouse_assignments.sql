CREATE TABLE warehouse_stock_assignments (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),request text NOT NULL,
 location text NOT NULL, product text NOT NULL, quantity numeric(18,3) NOT NULL CHECK(quantity>0),
 actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,request),
 FOREIGN KEY(tenant,location) REFERENCES store_locations(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
