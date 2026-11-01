-- Content-addressed assets preserve historical receipt identity across replacements.
CREATE TABLE IF NOT EXISTS business_logo_assets (
    sha256 char(64) PRIMARY KEY,
    media_type text NOT NULL CHECK (media_type = 'image/png'),
    content bytea NOT NULL CHECK (octet_length(content) <= 524288),
    created timestamptz NOT NULL DEFAULT now()
);
