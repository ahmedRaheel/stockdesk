ALTER TABLE products ADD COLUMN expiry_required boolean NOT NULL DEFAULT false;
ALTER TABLE products ADD COLUMN generic_name text NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN strength text NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN prescription_required boolean NOT NULL DEFAULT false;
ALTER TABLE sales ADD COLUMN prescription_reference text NOT NULL DEFAULT '';
CREATE TABLE stock_batches (
 id text PRIMARY KEY,tenant text NOT NULL,product text NOT NULL,lot text NOT NULL,
 expires date,stock numeric(18,3) NOT NULL CHECK(stock>=0),created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id),FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
INSERT INTO stock_batches(id,tenant,product,lot,stock)
 SELECT md5(tenant||':'||id||':UNTRACKED:'),tenant,id,'UNTRACKED',stock FROM products WHERE stock>0;
ALTER TABLE movements ADD COLUMN reason_id text;
ALTER TABLE movements ADD FOREIGN KEY(tenant,reason_id) REFERENCES lookups(tenant,id);
ALTER TABLE movements ADD COLUMN lot text NOT NULL DEFAULT '';
ALTER TABLE movements ADD COLUMN expires date;
ALTER TABLE movements ADD COLUMN batch_id text;
ALTER TABLE movements ADD COLUMN source_movement text REFERENCES movements(id);
ALTER TABLE movements ADD FOREIGN KEY(tenant,batch_id) REFERENCES stock_batches(tenant,id);
CREATE TABLE stock_batch_allocations (
 movement text NOT NULL REFERENCES movements(id),tenant text NOT NULL,batch text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity<>0), PRIMARY KEY(movement,batch),
 FOREIGN KEY(tenant,batch) REFERENCES stock_batches(tenant,id)
);
CREATE INDEX stock_batches_available ON stock_batches(tenant,product,expires,created);
CREATE FUNCTION allocate_stock_batches() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE chosen record;remaining numeric(18,3);take_qty numeric(18,3);batch_key text;needs_expiry boolean;
BEGIN
 IF NEW.quantity=0 THEN RETURN NEW; END IF;
 IF NEW.quantity>0 THEN
  IF NEW.type='RETURN' AND NEW.source_movement IS NOT NULL THEN
   remaining=NEW.quantity;
   FOR chosen IN SELECT a.* FROM stock_batch_allocations a JOIN stock_batches b ON b.tenant=a.tenant AND b.id=a.batch WHERE a.movement=NEW.source_movement AND a.tenant=NEW.tenant AND b.product=NEW.product AND a.quantity<0 LOOP
    UPDATE stock_batches SET stock=stock-chosen.quantity WHERE tenant=NEW.tenant AND id=chosen.batch;
    INSERT INTO stock_batch_allocations(movement,tenant,batch,quantity) VALUES(NEW.id,NEW.tenant,chosen.batch,-chosen.quantity);
    remaining=remaining+chosen.quantity;
   END LOOP;
   IF remaining<>0 THEN RAISE EXCEPTION 'Return allocation mismatch' USING ERRCODE='23514'; END IF;
   RETURN NEW;
  END IF;
  SELECT expiry_required INTO needs_expiry FROM products WHERE tenant=NEW.tenant AND id=NEW.product;
  IF needs_expiry AND (NEW.expires IS NULL OR NEW.lot='') THEN RAISE EXCEPTION 'Batch and expiry required' USING ERRCODE='23514'; END IF;
  batch_key=md5(NEW.tenant||':'||NEW.product||':'||COALESCE(NULLIF(NEW.lot,''),'UNTRACKED')||':'||COALESCE(NEW.expires::text,''));
  INSERT INTO stock_batches(id,tenant,product,lot,expires,stock) VALUES(batch_key,NEW.tenant,NEW.product,COALESCE(NULLIF(NEW.lot,''),'UNTRACKED'),NEW.expires,NEW.quantity)
   ON CONFLICT(id) DO UPDATE SET stock=stock_batches.stock+excluded.stock;
  INSERT INTO stock_batch_allocations(movement,tenant,batch,quantity) VALUES(NEW.id,NEW.tenant,batch_key,NEW.quantity);
 ELSE
  remaining=-NEW.quantity;
  FOR chosen IN SELECT * FROM stock_batches WHERE tenant=NEW.tenant AND product=NEW.product AND stock>0 AND (NEW.batch_id IS NULL OR id=NEW.batch_id) AND (NEW.type<>'SALE' OR expires IS NULL OR expires>=(now() AT TIME ZONE 'Asia/Karachi')::date) ORDER BY expires NULLS LAST,created,id FOR UPDATE LOOP
   take_qty=LEAST(remaining,chosen.stock);
   UPDATE stock_batches SET stock=stock-take_qty WHERE tenant=NEW.tenant AND id=chosen.id;
   INSERT INTO stock_batch_allocations(movement,tenant,batch,quantity) VALUES(NEW.id,NEW.tenant,chosen.id,-take_qty);
   remaining=remaining-take_qty;
   EXIT WHEN remaining=0;
  END LOOP;
  IF remaining<>0 THEN RAISE EXCEPTION 'Insufficient eligible batch stock' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER movement_batch_allocation AFTER INSERT ON movements FOR EACH ROW EXECUTE FUNCTION allocate_stock_batches();
