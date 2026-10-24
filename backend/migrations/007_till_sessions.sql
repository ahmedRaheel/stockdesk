CREATE TABLE till_sessions (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),actor text NOT NULL REFERENCES users(id),
 opening_cash bigint NOT NULL CHECK(opening_cash>=0),status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
 opened timestamptz NOT NULL DEFAULT now(),closed timestamptz,expected_cash bigint,counted_cash bigint,variance bigint,closing_note text,
 UNIQUE(tenant,id)
);
CREATE UNIQUE INDEX one_open_till_per_user ON till_sessions(tenant,actor) WHERE status='open';
CREATE TABLE till_cash_movements (
 id text PRIMARY KEY,tenant text NOT NULL,session text NOT NULL,request text NOT NULL,amount bigint NOT NULL CHECK(amount<>0),
 reason text NOT NULL,actor text NOT NULL,created timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant,request),
 FOREIGN KEY(tenant,session) REFERENCES till_sessions(tenant,id)
);
ALTER TABLE sales ADD COLUMN till_session text;
ALTER TABLE sales ADD FOREIGN KEY(tenant,till_session) REFERENCES till_sessions(tenant,id);
