-- Receipt provenance starts here; old free-text movement notes are not treated as proof.
CREATE TABLE purchase_receipt_sources (
 movement text PRIMARY KEY REFERENCES movements(id),tenant text NOT NULL,purchase text NOT NULL,
 receipt text NOT NULL REFERENCES purchase_receipts(id),product text NOT NULL,batch text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0),UNIQUE(tenant,movement),
 FOREIGN KEY(tenant,purchase) REFERENCES purchase_orders(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id),
 FOREIGN KEY(tenant,batch) REFERENCES stock_batches(tenant,id)
);
CREATE TABLE supplier_returns (
 id text PRIMARY KEY,tenant text NOT NULL,bill text NOT NULL,supplier text NOT NULL,
 request text NOT NULL,signature text NOT NULL,credit_number text NOT NULL,returned_on date NOT NULL,
 reason_id text NOT NULL,reason text NOT NULL,subtotal bigint NOT NULL CHECK(subtotal>=0),
 tax bigint NOT NULL CHECK(tax>=0),total bigint NOT NULL CHECK(total=subtotal+tax),
 actor text NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id),UNIQUE(tenant,request),UNIQUE(tenant,supplier,credit_number),
 FOREIGN KEY(tenant,bill) REFERENCES supplier_bills(tenant,id),
 FOREIGN KEY(tenant,supplier) REFERENCES suppliers(tenant,id),
 FOREIGN KEY(tenant,reason_id) REFERENCES lookups(tenant,id)
);
CREATE TABLE supplier_return_lines (
 tenant text NOT NULL,return_id text NOT NULL,product text NOT NULL,source text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0),subtotal bigint NOT NULL CHECK(subtotal>=0),
 movement text NOT NULL REFERENCES movements(id),
 PRIMARY KEY(tenant,return_id,source),FOREIGN KEY(tenant,return_id) REFERENCES supplier_returns(tenant,id),
 FOREIGN KEY(tenant,source) REFERENCES purchase_receipt_sources(tenant,movement),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE supplier_refunds (
 id text PRIMARY KEY,tenant text NOT NULL,bill text NOT NULL,request text NOT NULL,signature text NOT NULL,
 amount bigint NOT NULL CHECK(amount>0),method_id text NOT NULL,method_name text NOT NULL,
 reference text NOT NULL,received_on date NOT NULL,actor text NOT NULL,
 status text NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','void')),
 void_reason text,voided timestamptz,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request),FOREIGN KEY(tenant,bill) REFERENCES supplier_bills(tenant,id),
 FOREIGN KEY(tenant,method_id) REFERENCES lookups(tenant,id)
);
CREATE INDEX supplier_returns_bill ON supplier_returns(tenant,bill);
CREATE INDEX supplier_return_source ON supplier_return_lines(tenant,source);
CREATE INDEX supplier_refunds_bill ON supplier_refunds(tenant,bill);
CREATE VIEW supplier_bill_balances AS
 SELECT x.*,x.total-x.paid-x.credited+x.refunded AS balance FROM (
 SELECT b.tenant,b.id,b.total,
 COALESCE((SELECT SUM(amount) FROM supplier_payments p WHERE p.tenant=b.tenant AND p.bill=b.id AND p.status='posted'),0) AS paid,
 COALESCE((SELECT SUM(total) FROM supplier_returns r WHERE r.tenant=b.tenant AND r.bill=b.id),0) AS credited,
 COALESCE((SELECT SUM(amount) FROM supplier_refunds r WHERE r.tenant=b.tenant AND r.bill=b.id AND r.status='posted'),0) AS refunded
 FROM supplier_bills b) x;
