CREATE TABLE promotions (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id),
 code text NOT NULL CHECK(code ~ '^[A-Z0-9_-]{1,40}$'),
 name text NOT NULL, name_ur text NOT NULL DEFAULT '',
 kind text NOT NULL CHECK(kind IN ('fixed','percentage','bogo','bundle')),
 value bigint NOT NULL DEFAULT 0 CHECK(value BETWEEN 0 AND 100000000000),
 minimum_subtotal bigint NOT NULL DEFAULT 0 CHECK(minimum_subtotal BETWEEN 0 AND 100000000000),
 maximum_discount bigint CHECK(maximum_discount BETWEEN 1 AND 100000000000),
 buy_quantity integer NOT NULL DEFAULT 1 CHECK(buy_quantity BETWEEN 1 AND 1000000),
 free_quantity integer NOT NULL DEFAULT 1 CHECK(free_quantity BETWEEN 1 AND 1000000),
 starts_on date, ends_on date, starts_minute integer, ends_minute integer,
 usage_limit integer CHECK(usage_limit BETWEEN 1 AND 1000000000),
 active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id),UNIQUE(tenant,code),
 CHECK(ends_on IS NULL OR starts_on IS NULL OR ends_on>=starts_on),
 CHECK((starts_minute IS NULL AND ends_minute IS NULL) OR
       (starts_minute IS NOT NULL AND ends_minute IS NOT NULL AND starts_minute BETWEEN 0 AND 1439 AND ends_minute BETWEEN 1 AND 1440 AND ends_minute>starts_minute)),
 CHECK(kind<>'percentage' OR value BETWEEN 1 AND 10000),
 CHECK(kind<>'fixed' OR value>0)
);
CREATE TABLE promotion_items (
 tenant text NOT NULL,promotion text NOT NULL,product text NOT NULL,
 quantity numeric(12,3) NOT NULL CHECK(quantity>0 AND quantity<=1000000),
 PRIMARY KEY(tenant,promotion,product),
 FOREIGN KEY(tenant,promotion) REFERENCES promotions(tenant,id),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id)
);
CREATE TABLE promotion_redemptions (
 tenant text NOT NULL,promotion text NOT NULL,sale text NOT NULL,
 discount bigint NOT NULL CHECK(discount>0),created timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant,sale),
 FOREIGN KEY(tenant,promotion) REFERENCES promotions(tenant,id),
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
CREATE INDEX promotion_redemptions_usage ON promotion_redemptions(tenant,promotion);
ALTER TABLE sales ADD COLUMN promotion_snapshot jsonb NOT NULL DEFAULT '{}';
