-- Prices are integer minor units per catalog unit; breaks use total ordered quantity.
ALTER TABLE supplier_offers ADD CONSTRAINT supplier_offers_tenant_id UNIQUE(tenant,id);
CREATE TABLE supplier_offer_tiers (
 tenant text NOT NULL, offer text NOT NULL,
 minimum_quantity numeric(18,3) NOT NULL CHECK(minimum_quantity>0 AND minimum_quantity<=1000000),
 unit_cost bigint NOT NULL CHECK(unit_cost>=0 AND unit_cost<=100000000000),
 PRIMARY KEY(tenant,offer,minimum_quantity),
 FOREIGN KEY(tenant,offer) REFERENCES supplier_offers(tenant,id)
);
ALTER TABLE purchase_lines ADD COLUMN quote_snapshot jsonb;
