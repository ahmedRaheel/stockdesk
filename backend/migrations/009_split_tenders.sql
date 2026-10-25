ALTER TABLE sales ADD COLUMN cash_amount bigint NOT NULL DEFAULT 0 CHECK(cash_amount>=0);
UPDATE sales SET cash_amount=paid_now WHERE payment='cash';
CREATE TABLE sale_tenders (
 id text PRIMARY KEY,tenant text NOT NULL,sale text NOT NULL,method_id text,
 method_name text NOT NULL,method_name_ur text NOT NULL DEFAULT '',is_cash boolean NOT NULL,
 amount bigint NOT NULL CHECK(amount>0),reference text NOT NULL DEFAULT '',
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id),FOREIGN KEY(tenant,method_id) REFERENCES lookups(tenant,id)
);
CREATE INDEX sale_tenders_sale ON sale_tenders(tenant,sale);
