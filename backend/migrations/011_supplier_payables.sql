CREATE TABLE supplier_bills (
 id text PRIMARY KEY, tenant text NOT NULL, supplier text NOT NULL, purchase text NOT NULL,
 request text NOT NULL, signature text NOT NULL, invoice_number text NOT NULL,
 invoice_date date NOT NULL, due_date date NOT NULL CHECK(due_date>=invoice_date),
 subtotal bigint NOT NULL CHECK(subtotal>=0), tax bigint NOT NULL CHECK(tax>=0),
 total bigint NOT NULL CHECK(total=subtotal+tax AND total>0),
 status text NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','void')),
 actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 void_reason text, voided timestamptz,
 UNIQUE(tenant,id), UNIQUE(tenant,request), UNIQUE(tenant,supplier,invoice_number),
 FOREIGN KEY(tenant,supplier) REFERENCES suppliers(tenant,id),
 FOREIGN KEY(tenant,purchase) REFERENCES purchase_orders(tenant,id)
);
CREATE TABLE supplier_bill_lines (
 tenant text NOT NULL, bill text NOT NULL, product text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0), unit_cost bigint NOT NULL CHECK(unit_cost>=0),
 line_total bigint NOT NULL CHECK(line_total>=0),
 PRIMARY KEY(tenant,bill,product), FOREIGN KEY(tenant,bill) REFERENCES supplier_bills(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE supplier_payments (
 id text PRIMARY KEY, tenant text NOT NULL, bill text NOT NULL, request text NOT NULL, signature text NOT NULL,
 amount bigint NOT NULL CHECK(amount>0), method_id text NOT NULL, method_name text NOT NULL,
 reference text NOT NULL, paid_on date NOT NULL, actor text NOT NULL,
 status text NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','void')),
 created timestamptz NOT NULL DEFAULT now(), void_reason text, voided timestamptz,
 UNIQUE(tenant,id), UNIQUE(tenant,request), FOREIGN KEY(tenant,bill) REFERENCES supplier_bills(tenant,id),
 FOREIGN KEY(tenant,method_id) REFERENCES lookups(tenant,id)
);
CREATE INDEX supplier_bills_tenant_due ON supplier_bills(tenant,due_date,id);
CREATE INDEX supplier_payments_bill ON supplier_payments(tenant,bill);
