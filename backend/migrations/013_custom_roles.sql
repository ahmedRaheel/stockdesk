CREATE TABLE tenant_roles (
 id text PRIMARY KEY,tenant text NOT NULL REFERENCES tenants(id),name text NOT NULL,
 name_ur text NOT NULL DEFAULT '',active boolean NOT NULL DEFAULT true,
 version integer NOT NULL DEFAULT 1,created timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant,id),UNIQUE(tenant,name)
);
CREATE TABLE tenant_role_permissions (
 tenant text NOT NULL,role_id text NOT NULL,permission text NOT NULL,
 PRIMARY KEY(tenant,role_id,permission),FOREIGN KEY(tenant,role_id) REFERENCES tenant_roles(tenant,id)
);
ALTER TABLE members ADD COLUMN custom_role_id text;
ALTER TABLE members ADD FOREIGN KEY(tenant,custom_role_id) REFERENCES tenant_roles(tenant,id);
ALTER TABLE members ADD CONSTRAINT owner_has_no_custom_role CHECK(role<>'Owner' OR custom_role_id IS NULL);
