ALTER TABLE inventory_alert_rules DROP CONSTRAINT inventory_alert_rules_kind_check;
ALTER TABLE inventory_alert_rules ADD CONSTRAINT inventory_alert_rules_kind_check CHECK(kind IN ('low_stock','stock_out','expiry','customer_overdue','supplier_overdue','cash_variance'));
ALTER TABLE inventory_alert_rules ADD COLUMN minimum_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK(minimum_amount BETWEEN 0 AND 1000000000);
ALTER TABLE inventory_alert_rules ADD COLUMN overdue_days integer NOT NULL DEFAULT 0 CHECK(overdue_days BETWEEN 0 AND 3650);
ALTER TABLE inventory_alert_rules ADD COLUMN lookback_days integer NOT NULL DEFAULT 30 CHECK(lookback_days BETWEEN 1 AND 365);
ALTER TABLE inventory_alert_rules ADD CONSTRAINT finance_alert_scope CHECK(kind IN ('low_stock','stock_out','expiry') OR (product IS NULL AND threshold IS NULL));
CREATE INDEX receivables_alert_due ON receivables(tenant,due_date,id) WHERE status='open';
CREATE INDEX till_alert_closed ON till_sessions(tenant,closed,id) WHERE status='closed' AND variance<>0;
