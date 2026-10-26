ALTER TABLE customer_payments ADD COLUMN method_name text NOT NULL DEFAULT '';
ALTER TABLE customer_payments ADD COLUMN method_name_ur text NOT NULL DEFAULT '';
ALTER TABLE customer_payments ADD COLUMN is_cash boolean NOT NULL DEFAULT false;
UPDATE customer_payments p SET method_name=l.name,method_name_ur=l.name_ur,is_cash=(l.code='cash') FROM lookups l WHERE l.tenant=p.tenant AND l.id=p.method;
ALTER TABLE sale_tenders ADD COLUMN origin jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE sale_adjustments DROP CONSTRAINT sale_adjustments_settlement_check;
ALTER TABLE sale_adjustments ADD CONSTRAINT sale_adjustments_settlement_check CHECK(settlement IN ('cash','external','original'));
ALTER TABLE sale_tenders ADD COLUMN carried_credit boolean NOT NULL DEFAULT false;
