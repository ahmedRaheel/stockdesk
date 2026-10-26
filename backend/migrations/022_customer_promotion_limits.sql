ALTER TABLE promotions ADD COLUMN per_customer_limit integer CHECK(per_customer_limit BETWEEN 1 AND 1000000000);
ALTER TABLE promotion_redemptions ADD COLUMN customer text;
ALTER TABLE promotion_redemptions ADD FOREIGN KEY(tenant,customer) REFERENCES customers(tenant,id);
UPDATE promotion_redemptions r SET customer=s.customer_id FROM sales s WHERE s.tenant=r.tenant AND s.id=r.sale;
CREATE INDEX promotion_redemptions_customer_usage ON promotion_redemptions(tenant,promotion,customer);
