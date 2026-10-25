ALTER TABLE products ADD COLUMN stock_revision bigint NOT NULL DEFAULT 0;
CREATE FUNCTION increment_stock_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN UPDATE products SET stock_revision=stock_revision+1 WHERE tenant=NEW.tenant AND id=NEW.product;RETURN NEW;END $$;
CREATE TRIGGER movement_stock_revision AFTER INSERT ON movements FOR EACH ROW EXECUTE FUNCTION increment_stock_revision();
CREATE TABLE stock_counts (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),request text NOT NULL,signature text NOT NULL,
 reference text NOT NULL,status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','posted','cancelled')),
 created_by text NOT NULL REFERENCES users(id),approved_by text REFERENCES users(id),note text NOT NULL DEFAULT '',
 created timestamptz NOT NULL DEFAULT now(),submitted timestamptz,posted timestamptz,UNIQUE(tenant,id),UNIQUE(tenant,request)
);
CREATE TABLE stock_count_lines (
 tenant text NOT NULL,count_id text NOT NULL,product text NOT NULL,batch text NOT NULL,
 expected numeric(18,3) NOT NULL,revision bigint NOT NULL,counted numeric(18,3) CHECK(counted>=0),
 PRIMARY KEY(count_id,batch),FOREIGN KEY(tenant,count_id) REFERENCES stock_counts(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id),FOREIGN KEY(tenant,batch) REFERENCES stock_batches(tenant,id)
);
CREATE INDEX stock_counts_tenant_date ON stock_counts(tenant,created DESC);
