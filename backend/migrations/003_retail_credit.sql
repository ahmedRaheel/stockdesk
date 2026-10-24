-- Reference data is tenant-owned. Codes remain stable; labels may be translated.
CREATE TABLE lookups (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id),
 kind text NOT NULL CHECK(kind IN ('category','unit','payment_method','adjustment_reason','return_reason','customer_segment')),
 code text NOT NULL, name text NOT NULL, name_ur text NOT NULL DEFAULT '',
 active boolean NOT NULL DEFAULT true, sort_order integer NOT NULL DEFAULT 0,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,kind,code)
);
CREATE FUNCTION seed_retail_lookups(tid text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO lookups(id,tenant,kind,code,name,name_ur,sort_order)
 SELECT md5(tid||v.kind||v.code),tid,v.kind,v.code,v.name,v.urdu,v.sort_order FROM (VALUES
 ('category','general','General','جنرل',0),('category','pantry','Pantry','کریانہ',1),
 ('category','produce','Fruit and vegetables','پھل اور سبزیاں',2),('category','medicine','Medicine','ادویات',3),
 ('unit','piece','Piece','عدد',0),('unit','kg','Kilogram','کلوگرام',1),('unit','dozen','Dozen','درجن',2),('unit','litre','Litre','لیٹر',3),('unit','pack','Pack','پیکٹ',4),
 ('payment_method','cash','Cash','نقد',0),('payment_method','bank','Bank transfer','بینک ٹرانسفر',1),('payment_method','jazzcash','JazzCash','جاز کیش',2),('payment_method','easypaisa','Easypaisa','ایزی پیسہ',3),('payment_method','raast','Raast','راست',4),('payment_method','card','Card (collected externally)','کارڈ',5),
 ('adjustment_reason','damage','Damage','نقصان',0),('adjustment_reason','wastage','Wastage','ضیاع',1),('adjustment_reason','expiry','Expired','میعاد ختم',2),('adjustment_reason','count','Count correction','گنتی کی درستگی',3),
 ('return_reason','customer','Customer return','واپسی',0),('return_reason','defective','Defective item','خراب مال',1),
 ('customer_segment','retail','Retail','پرچون',0),('customer_segment','wholesale','Wholesale','تھوک',1)
 ) AS v(kind,code,name,urdu,sort_order) ON CONFLICT(tenant,kind,code) DO NOTHING;
END $$;
SELECT seed_retail_lookups(id) FROM tenants;
CREATE FUNCTION seed_new_tenant_lookups() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM seed_retail_lookups(NEW.id); RETURN NEW; END $$;
CREATE TRIGGER new_tenant_lookups AFTER INSERT ON tenants FOR EACH ROW EXECUTE FUNCTION seed_new_tenant_lookups();
INSERT INTO lookups(id,tenant,kind,code,name)
 SELECT md5(tenant||'legacy-category'||category),tenant,'category','legacy-'||md5(category),category FROM products GROUP BY tenant,category
 ON CONFLICT DO NOTHING;
ALTER TABLE products ADD COLUMN category_id text;
ALTER TABLE products ADD COLUMN unit_id text;
ALTER TABLE products ADD COLUMN search_aliases text NOT NULL DEFAULT '';
UPDATE products p SET category_id=(SELECT l.id FROM lookups l WHERE l.tenant=p.tenant AND l.kind='category' AND l.name=p.category ORDER BY l.code LIMIT 1),unit_id=md5(p.tenant||'unitpiece');
ALTER TABLE products ADD FOREIGN KEY(tenant,category_id) REFERENCES lookups(tenant,id);
ALTER TABLE products ADD FOREIGN KEY(tenant,unit_id) REFERENCES lookups(tenant,id);
CREATE TABLE customers (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), name text NOT NULL,
 phone text NOT NULL DEFAULT '', search_aliases text NOT NULL DEFAULT '', address text NOT NULL DEFAULT '',
 reference_contact text NOT NULL DEFAULT '', active boolean NOT NULL DEFAULT true,
 credit_limit bigint NOT NULL DEFAULT 0 CHECK(credit_limit>=0), credit_enabled boolean NOT NULL DEFAULT false,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id)
);
CREATE INDEX customers_tenant_name ON customers(tenant,name,id);
CREATE TABLE credit_requests (
 id text PRIMARY KEY, tenant text NOT NULL, customer text NOT NULL,
 proposed_limit bigint NOT NULL CHECK(proposed_limit>=0), reason text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 requested_by text NOT NULL REFERENCES users(id), decided_by text REFERENCES users(id), decision_note text,
 created timestamptz NOT NULL DEFAULT now(), decided timestamptz,
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id)
);
ALTER TABLE sales ADD COLUMN customer_id text;
ALTER TABLE sales ADD COLUMN paid_now bigint NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN credit_amount bigint NOT NULL DEFAULT 0 CHECK(credit_amount>=0);
ALTER TABLE sales ADD COLUMN payment_method_id text;
ALTER TABLE sales ADD FOREIGN KEY(tenant,customer_id) REFERENCES customers(tenant,id);
ALTER TABLE sales ADD FOREIGN KEY(tenant,payment_method_id) REFERENCES lookups(tenant,id);
UPDATE sales SET paid_now=total;
CREATE TABLE receivables (
 id text PRIMARY KEY, tenant text NOT NULL, customer text NOT NULL, sale text NOT NULL,
 principal bigint NOT NULL CHECK(principal>0), due_date date NOT NULL,
 status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','settled','cancelled')),
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,sale),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id), FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
CREATE TABLE customer_ledger (
 id text PRIMARY KEY, tenant text NOT NULL, customer text NOT NULL, receivable text,
 kind text NOT NULL CHECK(kind IN ('sale','recovery','return','markup','waiver')),
 amount bigint NOT NULL CHECK(amount<>0), reference text NOT NULL, actor text NOT NULL,
 created timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id), FOREIGN KEY(tenant,receivable) REFERENCES receivables(tenant,id)
);
CREATE INDEX customer_ledger_account ON customer_ledger(tenant,customer,created,id);
CREATE FUNCTION reject_ledger_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Posted customer ledger entries are immutable; post a reversal'; END $$;
CREATE TRIGGER customer_ledger_immutable BEFORE UPDATE OR DELETE ON customer_ledger FOR EACH ROW EXECUTE FUNCTION reject_ledger_change();
CREATE TABLE customer_payments (
 id text PRIMARY KEY, tenant text NOT NULL, customer text NOT NULL, request text NOT NULL, signature text NOT NULL,
 amount bigint NOT NULL CHECK(amount>0), method text NOT NULL, reference text NOT NULL DEFAULT '',
 actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,request),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id), FOREIGN KEY(tenant,method) REFERENCES lookups(tenant,id)
);
CREATE TABLE payment_allocations (
 tenant text NOT NULL,payment text NOT NULL,receivable text NOT NULL, amount bigint NOT NULL CHECK(amount>0),
 PRIMARY KEY(tenant,payment,receivable), FOREIGN KEY(tenant,payment) REFERENCES customer_payments(tenant,id),
 FOREIGN KEY(tenant,receivable) REFERENCES receivables(tenant,id)
);
CREATE TABLE installment_plans (
 id text PRIMARY KEY, tenant text NOT NULL,receivable text NOT NULL, frequency text NOT NULL CHECK(frequency IN ('weekly','fortnightly','monthly')),
 installments integer NOT NULL CHECK(installments BETWEEN 1 AND 60), markup bigint NOT NULL CHECK(markup>=0),
 agreed_total bigint NOT NULL CHECK(agreed_total>0), first_due date NOT NULL,actor text NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id),UNIQUE(tenant,receivable),FOREIGN KEY(tenant,receivable) REFERENCES receivables(tenant,id)
);
CREATE TABLE installment_schedule (
 id text PRIMARY KEY,tenant text NOT NULL,plan text NOT NULL,sequence integer NOT NULL,due_date date NOT NULL,
 amount bigint NOT NULL CHECK(amount>0), paid bigint NOT NULL DEFAULT 0 CHECK(paid>=0 AND paid<=amount),
 UNIQUE(tenant,plan,sequence),FOREIGN KEY(tenant,plan) REFERENCES installment_plans(tenant,id)
);
CREATE TABLE payment_promises (
 id text PRIMARY KEY,tenant text NOT NULL,customer text NOT NULL,promised_date date NOT NULL,
 amount bigint NOT NULL CHECK(amount>0),notes text NOT NULL DEFAULT '',actor text NOT NULL,created timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id)
);
CREATE TABLE held_bills (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),actor text NOT NULL REFERENCES users(id),label text NOT NULL,
 payload jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant,id)
);
