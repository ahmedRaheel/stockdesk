ALTER TABLE inventory_alert_rules ADD COLUMN escalate_after_minutes integer CHECK(escalate_after_minutes BETWEEN 1 AND 10080);
ALTER TABLE inventory_alert_rules ADD CONSTRAINT escalation_noncritical CHECK(escalate_after_minutes IS NULL OR severity<>'critical');
ALTER TABLE inventory_alerts ADD COLUMN escalated_at timestamptz;
ALTER TABLE inventory_alerts ADD COLUMN escalated_from text;
ALTER TABLE inventory_alerts ADD COLUMN escalation_minutes integer;
ALTER TABLE inventory_alerts ADD CONSTRAINT escalation_history CHECK(
 (escalated_at IS NULL AND escalated_from IS NULL AND escalation_minutes IS NULL)
 OR (escalated_at IS NOT NULL AND escalated_from IS NOT NULL AND escalation_minutes IS NOT NULL AND escalated_from IN ('info','warning') AND escalation_minutes BETWEEN 1 AND 10080 AND severity='critical'));
