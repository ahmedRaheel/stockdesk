ALTER TABLE promotions ADD COLUMN stackable boolean NOT NULL DEFAULT false;
ALTER TABLE promotion_redemptions DROP CONSTRAINT promotion_redemptions_pkey;
ALTER TABLE promotion_redemptions ADD PRIMARY KEY(tenant,sale,promotion);
