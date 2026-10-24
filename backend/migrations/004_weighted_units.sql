ALTER TABLE lookups ADD COLUMN fractional boolean NOT NULL DEFAULT false;
UPDATE lookups SET fractional=true WHERE kind='unit' AND code IN ('kg','litre');
CREATE FUNCTION seed_fractional_units() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.kind='unit' AND NEW.code IN ('kg','litre') THEN NEW.fractional=true; END IF; RETURN NEW; END $$;
CREATE TRIGGER unit_fractional_defaults BEFORE INSERT ON lookups FOR EACH ROW EXECUTE FUNCTION seed_fractional_units();
ALTER TABLE products ALTER COLUMN stock TYPE numeric(18,3);
ALTER TABLE products ALTER COLUMN reorder TYPE numeric(18,3);
ALTER TABLE movements ALTER COLUMN quantity TYPE numeric(18,3);
ALTER TABLE sale_items ALTER COLUMN quantity TYPE numeric(18,3);
ALTER TABLE sale_items ADD COLUMN unit_name text NOT NULL DEFAULT 'Piece';
ALTER TABLE sale_items ADD COLUMN line_total bigint;
UPDATE sale_items SET line_total=round(quantity*price)::bigint;
ALTER TABLE sale_items ALTER COLUMN line_total SET NOT NULL;
ALTER TABLE purchase_lines ALTER COLUMN quantity TYPE numeric(18,3);
ALTER TABLE purchase_lines ALTER COLUMN received TYPE numeric(18,3);
