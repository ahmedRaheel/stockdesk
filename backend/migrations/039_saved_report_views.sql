CREATE TABLE saved_report_views (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), name text NOT NULL,
 definition jsonb NOT NULL, version integer NOT NULL DEFAULT 1,
 created_by text NOT NULL, created timestamptz NOT NULL DEFAULT now(), updated timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,name), UNIQUE(tenant,id)
);
