-- Preserve checkout evidence while maintaining a current invoice revision.
ALTER TABLE sales ADD COLUMN revision integer NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN original_snapshot jsonb;
CREATE TABLE sale_adjustments (
 id text PRIMARY KEY, tenant text NOT NULL, sale text NOT NULL, request text NOT NULL,
 signature text NOT NULL, revision integer NOT NULL, credit bigint NOT NULL CHECK(credit>=0),
 replacement_sale text, settlement text NOT NULL CHECK(settlement IN ('cash','external')),
 net bigint NOT NULL, tendered bigint NOT NULL, reference text NOT NULL,
 before_snapshot jsonb NOT NULL, details jsonb NOT NULL, result jsonb NOT NULL,
 actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request), UNIQUE(tenant,sale,revision),
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id),
 FOREIGN KEY(tenant,replacement_sale) REFERENCES sales(tenant,id)
);
-- A partial customer return targets one previously sold batch, including expired batches.
CREATE FUNCTION restore_selected_return_batch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.type='RETURN' AND NEW.batch_id IS NOT NULL AND NEW.source_movement IS NULL THEN
  IF NEW.quantity<=0 OR NOT EXISTS(SELECT 1 FROM stock_batches WHERE tenant=NEW.tenant AND id=NEW.batch_id AND product=NEW.product) THEN
   RAISE EXCEPTION 'Invalid returned batch' USING ERRCODE='23514';
  END IF;
  UPDATE stock_batches SET stock=stock+NEW.quantity WHERE tenant=NEW.tenant AND id=NEW.batch_id;
  INSERT INTO stock_batch_allocations(movement,tenant,batch,quantity) VALUES(NEW.id,NEW.tenant,NEW.batch_id,NEW.quantity);
 END IF;
 RETURN NEW;
END $$;
-- Replace the original batch trigger with a dispatcher; leave its tested legacy function intact.
DROP TRIGGER movement_batch_allocation ON movements;
CREATE TRIGGER movement_batch_allocation AFTER INSERT ON movements FOR EACH ROW
 WHEN (NOT (NEW.type='RETURN' AND NEW.batch_id IS NOT NULL AND NEW.source_movement IS NULL)) EXECUTE FUNCTION allocate_stock_batches();
CREATE TRIGGER movement_selected_return AFTER INSERT ON movements FOR EACH ROW
 WHEN (NEW.type='RETURN' AND NEW.batch_id IS NOT NULL AND NEW.source_movement IS NULL) EXECUTE FUNCTION restore_selected_return_batch();
