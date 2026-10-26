-- Variants remain ordinary, independently priced and stocked product SKUs.
ALTER TABLE products ADD COLUMN variant_revision integer NOT NULL DEFAULT 0;
CREATE TABLE product_families (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), request text NOT NULL,
 signature text NOT NULL, name text NOT NULL, axes jsonb NOT NULL,
 active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,id), UNIQUE(tenant,request)
);
CREATE UNIQUE INDEX product_family_name ON product_families(tenant,lower(name));
CREATE TABLE product_variants (
 tenant text NOT NULL, product text NOT NULL, family text NOT NULL,
 attributes jsonb NOT NULL, combination text NOT NULL, version integer NOT NULL DEFAULT 1,
 PRIMARY KEY(tenant,product), UNIQUE(tenant,family,combination),
 FOREIGN KEY(tenant,product) REFERENCES products(tenant,id),
 FOREIGN KEY(tenant,family) REFERENCES product_families(tenant,id)
);
CREATE TABLE assembly_recipes (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), request text NOT NULL,
 signature text NOT NULL, name text NOT NULL, kind text NOT NULL CHECK(kind IN ('bom','pack')),
 output text NOT NULL, components jsonb NOT NULL, version integer NOT NULL DEFAULT 1,
 active boolean NOT NULL DEFAULT true, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id), UNIQUE(tenant,request), UNIQUE(tenant,output),
 FOREIGN KEY(tenant,output) REFERENCES products(tenant,id)
);
CREATE TABLE assembly_jobs (
 id text PRIMARY KEY, tenant text NOT NULL, recipe text NOT NULL, request text NOT NULL,
 signature text NOT NULL, direction text NOT NULL CHECK(direction IN ('build','unpack')),
 quantity numeric(18,3) NOT NULL CHECK(quantity>0), snapshot jsonb NOT NULL,
 result jsonb NOT NULL, actor text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,request), FOREIGN KEY(tenant,recipe) REFERENCES assembly_recipes(tenant,id)
);
CREATE INDEX assembly_jobs_history ON assembly_jobs(tenant,created DESC,id);
CREATE TRIGGER assembly_job_immutable BEFORE UPDATE OR DELETE ON assembly_jobs
 FOR EACH ROW EXECUTE FUNCTION reject_ledger_change();
CREATE VIEW product_variant_labels AS
 SELECT v.tenant,v.product,f.name || ' · ' || string_agg(a.key || ': ' || a.value,' · ' ORDER BY a.key) AS label
 FROM product_variants v JOIN product_families f ON f.tenant=v.tenant AND f.id=v.family
 CROSS JOIN LATERAL jsonb_each_text(v.attributes) a GROUP BY v.tenant,v.product,f.name;
