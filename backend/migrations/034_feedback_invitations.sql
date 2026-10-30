ALTER TABLE customer_feedback ADD COLUMN source text NOT NULL DEFAULT 'staff' CHECK(source IN ('staff','customer'));
CREATE UNIQUE INDEX one_customer_feedback_per_sale ON customer_feedback(tenant,sale) WHERE source='customer';
CREATE TABLE feedback_invitations (
 id text PRIMARY KEY, tenant text NOT NULL, sale text NOT NULL, token_hash text NOT NULL UNIQUE,
 expires timestamptz NOT NULL, revoked timestamptz, submitted timestamptz,
 feedback text, created_by text NOT NULL, created timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0, window_start timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id), FOREIGN KEY(tenant,sale) REFERENCES sales(tenant,id),
 FOREIGN KEY(tenant,feedback) REFERENCES customer_feedback(tenant,id),
 CHECK((submitted IS NULL AND feedback IS NULL) OR (submitted IS NOT NULL AND feedback IS NOT NULL))
);
CREATE UNIQUE INDEX one_active_feedback_invitation ON feedback_invitations(tenant,sale) WHERE revoked IS NULL AND submitted IS NULL;
CREATE INDEX feedback_invitation_history ON feedback_invitations(tenant,created DESC,id);
