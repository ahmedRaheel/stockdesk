-- Keep actual payments separate from return credits on installment schedules.
ALTER TABLE installment_schedule ADD COLUMN credited bigint NOT NULL DEFAULT 0;
ALTER TABLE installment_schedule ADD CONSTRAINT installment_credit_bounds CHECK(credited>=0 AND paid+credited<=amount);
