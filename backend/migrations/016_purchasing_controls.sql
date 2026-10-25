CREATE TABLE purchasing_policies (
 tenant text PRIMARY KEY REFERENCES tenants(id),enabled boolean NOT NULL DEFAULT false,
 threshold bigint NOT NULL DEFAULT 0 CHECK(threshold>=0),version integer NOT NULL DEFAULT 1
);
ALTER TABLE purchase_orders DROP CONSTRAINT purchase_orders_status_check;
ALTER TABLE purchase_orders ADD CONSTRAINT purchase_orders_status_check CHECK(status IN ('open','pending_approval','rejected','partial','received','cancelled'));
ALTER TABLE purchase_orders ADD COLUMN approval_required boolean NOT NULL DEFAULT false;
ALTER TABLE purchase_orders ADD COLUMN approval_threshold bigint;
ALTER TABLE purchase_orders ADD COLUMN order_total bigint;
ALTER TABLE purchase_orders ADD COLUMN lead_days_snapshot integer;
ALTER TABLE purchase_orders ADD COLUMN decided_by text REFERENCES users(id);
ALTER TABLE purchase_orders ADD COLUMN decided_on timestamptz;
ALTER TABLE purchase_orders ADD COLUMN decision text CHECK(decision IN ('approve','reject'));
ALTER TABLE purchase_orders ADD COLUMN decision_note text;
UPDATE purchase_orders o SET order_total=(SELECT COALESCE(SUM(round(quantity*unit_cost)),0) FROM purchase_lines l WHERE l.tenant=o.tenant AND l.purchase=o.id);
ALTER TABLE purchase_orders ALTER COLUMN order_total SET NOT NULL;
ALTER TABLE purchase_orders ALTER COLUMN order_total SET DEFAULT 0;
CREATE TABLE supplier_offers (
 id text PRIMARY KEY,tenant text NOT NULL,supplier text NOT NULL,product text NOT NULL,
 unit_cost bigint NOT NULL CHECK(unit_cost>=0),minimum_quantity numeric(18,3) NOT NULL CHECK(minimum_quantity>0),
 lead_days integer NOT NULL CHECK(lead_days BETWEEN 0 AND 365),valid_from date NOT NULL,valid_until date,
 active boolean NOT NULL DEFAULT true,version integer NOT NULL DEFAULT 1,notes text NOT NULL DEFAULT '',
 created timestamptz NOT NULL DEFAULT now(),updated timestamptz NOT NULL DEFAULT now(),
 CHECK(valid_until IS NULL OR valid_until>=valid_from),UNIQUE(tenant,supplier,product),
 FOREIGN KEY(tenant,supplier) REFERENCES suppliers(tenant,id),FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE INDEX supplier_offers_product ON supplier_offers(tenant,product,unit_cost);
