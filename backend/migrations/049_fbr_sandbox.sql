-- Sandbox-only FBR DI integration; not evidence of fiscal certification.
CREATE TABLE fbr_sandbox_credentials (
 tenant text PRIMARY KEY REFERENCES tenants(id), token_enc text NOT NULL,
 configured_by text NOT NULL, updated timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE fbr_sandbox_validations (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), sale text NOT NULL,
 request text NOT NULL, payload_sha256 char(64) NOT NULL,
 response jsonb, status text NOT NULL CHECK(status IN ('pending','validated','rejected','uncertain')),
 created timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant,request),
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id)
);
CREATE INDEX fbr_validations_by_sale ON fbr_sandbox_validations(tenant,sale,created);
