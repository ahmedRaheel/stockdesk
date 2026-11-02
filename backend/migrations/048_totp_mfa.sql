-- Encrypted authenticator secrets; every code can be consumed only once.
CREATE TABLE user_mfa (
 user_id text PRIMARY KEY REFERENCES users(id),
 secret_enc text NOT NULL,
 enabled boolean NOT NULL DEFAULT false,
 enrolled timestamptz NOT NULL DEFAULT now(),
 enabled_at timestamptz,
 last_used_step bigint NOT NULL DEFAULT -1
);
