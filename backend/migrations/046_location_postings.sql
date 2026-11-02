-- Optional explicit location posting for sales and supplier receipts.
-- Legacy unlocated documents remain unchanged and must be reconciled separately.
ALTER TABLE sales ADD COLUMN location text;
ALTER TABLE sales ADD CONSTRAINT sales_location_fk FOREIGN KEY(tenant,location)
    REFERENCES store_locations(tenant,id);
ALTER TABLE purchase_receipts ADD COLUMN location text;
ALTER TABLE purchase_receipts ADD CONSTRAINT purchase_receipts_location_fk FOREIGN KEY(tenant,location)
    REFERENCES store_locations(tenant,id);
CREATE INDEX sales_by_location ON sales(tenant,location,created) WHERE location IS NOT NULL;
