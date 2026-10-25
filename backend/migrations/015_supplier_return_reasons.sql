ALTER TABLE lookups DROP CONSTRAINT lookups_kind_check;
ALTER TABLE lookups ADD CONSTRAINT lookups_kind_check CHECK(kind IN ('category','unit','payment_method','adjustment_reason','return_reason','customer_segment','supplier_return_reason'));
CREATE FUNCTION seed_supplier_return_reasons(tid text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO lookups(id,tenant,kind,code,name,name_ur,sort_order)
 SELECT md5(tid||'supplier_return_reason'||v.code),tid,'supplier_return_reason',v.code,v.name,v.urdu,v.sort_order
 FROM (VALUES ('damaged','Damaged goods','خراب مال',0),('expired','Expired or near expiry','میعاد ختم یا قریب',1),('wrong_item','Wrong item delivered','غلط مال موصول',2),('overstock','Agreed overstock return','طے شدہ اضافی مال کی واپسی',3)) AS v(code,name,urdu,sort_order)
 ON CONFLICT(tenant,kind,code) DO NOTHING;
END $$;
SELECT seed_supplier_return_reasons(id) FROM tenants;
CREATE FUNCTION seed_new_supplier_return_reasons() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM seed_supplier_return_reasons(NEW.id); RETURN NEW; END $$;
CREATE TRIGGER new_supplier_return_reasons AFTER INSERT ON tenants FOR EACH ROW EXECUTE FUNCTION seed_new_supplier_return_reasons();
