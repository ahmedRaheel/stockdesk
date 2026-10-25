-- Existing tenants retain explicitly named legacy manual mode until configured.
CREATE TABLE tax_profiles (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id),
 name text NOT NULL,name_ur text NOT NULL DEFAULT '',rate_bps integer NOT NULL CHECK(rate_bps BETWEEN 0 AND 10000),
 inclusive boolean NOT NULL DEFAULT false,active boolean NOT NULL DEFAULT true,
 starts_on date,ends_on date,UNIQUE(tenant,id),CHECK(ends_on IS NULL OR starts_on IS NULL OR ends_on>=starts_on)
);
ALTER TABLE tenants ADD COLUMN tax_mode text NOT NULL DEFAULT 'manual' CHECK(tax_mode IN ('manual','configured','disabled'));
ALTER TABLE tenants ADD COLUMN default_tax_profile text;
ALTER TABLE tenants ADD FOREIGN KEY(id,default_tax_profile) REFERENCES tax_profiles(tenant,id);
ALTER TABLE products ADD COLUMN tax_profile_id text;
ALTER TABLE products ADD FOREIGN KEY(tenant,tax_profile_id) REFERENCES tax_profiles(tenant,id);
ALTER TABLE sales ADD COLUMN tax_included bigint NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN tax_snapshot jsonb NOT NULL DEFAULT '{}';
ALTER TABLE sales ADD COLUMN return_reason_id text;
ALTER TABLE sales ADD FOREIGN KEY(tenant,return_reason_id) REFERENCES lookups(tenant,id);
