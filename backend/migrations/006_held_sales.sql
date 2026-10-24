ALTER TABLE held_bills ADD COLUMN consumed_sale text;
ALTER TABLE held_bills ADD FOREIGN KEY(tenant,consumed_sale) REFERENCES sales(tenant,id);
CREATE INDEX held_bills_owner ON held_bills(tenant,actor,created DESC);
