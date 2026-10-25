ALTER TABLE promotions DROP CONSTRAINT promotions_kind_check;
ALTER TABLE promotions ADD CONSTRAINT promotions_kind_check CHECK(kind IN ('fixed','percentage','bogo','bundle','cross_bogo'));
ALTER TABLE promotions ADD COLUMN reward_product text;
ALTER TABLE promotions ADD FOREIGN KEY(tenant,reward_product) REFERENCES products(tenant,id);
ALTER TABLE promotions ADD CONSTRAINT cross_bogo_reward CHECK((kind='cross_bogo' AND reward_product IS NOT NULL AND value=0) OR (kind<>'cross_bogo' AND reward_product IS NULL));
