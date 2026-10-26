ALTER TABLE tenants ADD COLUMN discount_approval_required boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN void_approval_required boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN transaction_policy_version integer NOT NULL DEFAULT 1;
CREATE TABLE transaction_approvals (
 id text PRIMARY KEY, tenant text NOT NULL REFERENCES tenants(id), request text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('discount','return','adjustment')), sale text,
 fingerprint text NOT NULL, payload jsonb NOT NULL, summary jsonb NOT NULL,
 requester text NOT NULL REFERENCES users(id), requester_email text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','consumed')),
 decision_by text REFERENCES users(id), decision_email text, note text NOT NULL DEFAULT '',
 created timestamptz NOT NULL DEFAULT now(), expires timestamptz NOT NULL DEFAULT now()+interval '30 minutes',
 decided timestamptz, consumed timestamptz,
 UNIQUE(tenant,request), UNIQUE(tenant,id),
 FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id),
 CHECK(decision_by IS NULL OR decision_by<>requester)
);
CREATE INDEX transaction_approval_queue ON transaction_approvals(tenant,status,created);
