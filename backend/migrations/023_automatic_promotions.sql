ALTER TABLE promotions ADD COLUMN automatic boolean NOT NULL DEFAULT false;
CREATE INDEX promotions_automatic ON promotions(tenant,code) WHERE active AND automatic;
