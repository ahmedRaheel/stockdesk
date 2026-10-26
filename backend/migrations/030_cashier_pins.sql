CREATE TABLE cashier_pins (
 tenant text NOT NULL REFERENCES tenants(id), user_id text NOT NULL REFERENCES users(id),
 pin_hash text NOT NULL, revision integer NOT NULL DEFAULT 1, updated timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant,user_id), FOREIGN KEY(tenant,user_id) REFERENCES members(tenant,user_id)
);
ALTER TABLE sessions ADD COLUMN tenant_scope text REFERENCES tenants(id);
ALTER TABLE sessions ADD COLUMN pin_revision integer;
ALTER TABLE sessions ADD CONSTRAINT session_pin_scope CHECK ((tenant_scope IS NULL) = (pin_revision IS NULL));
CREATE FUNCTION revoke_changed_cashier_membership() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.active IS DISTINCT FROM OLD.active OR NEW.role IS DISTINCT FROM OLD.role OR NEW.custom_role_id IS DISTINCT FROM OLD.custom_role_id THEN
  DELETE FROM sessions WHERE tenant_scope=NEW.tenant AND user_id=NEW.user_id;
  DELETE FROM cashier_pins WHERE tenant=NEW.tenant AND user_id=NEW.user_id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cashier_membership_changed AFTER UPDATE OF active,role,custom_role_id ON members FOR EACH ROW EXECUTE FUNCTION revoke_changed_cashier_membership();
CREATE FUNCTION revoke_changed_cashier_account() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.active IS DISTINCT FROM OLD.active OR NEW.is_admin IS DISTINCT FROM OLD.is_admin THEN
  DELETE FROM sessions WHERE tenant_scope IS NOT NULL AND user_id=NEW.id;
  DELETE FROM cashier_pins WHERE user_id=NEW.id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cashier_account_changed AFTER UPDATE OF active,is_admin ON users FOR EACH ROW EXECUTE FUNCTION revoke_changed_cashier_account();
