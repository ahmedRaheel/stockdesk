ALTER TABLE promotions ADD COLUMN weekdays smallint[] NOT NULL DEFAULT ARRAY[0,1,2,3,4,5,6]::smallint[];
ALTER TABLE promotions ADD CONSTRAINT promotion_weekday_bounds CHECK(cardinality(weekdays) BETWEEN 1 AND 7 AND weekdays <@ ARRAY[0,1,2,3,4,5,6]::smallint[] AND array_position(weekdays,NULL) IS NULL);
-- Replace only the original daily-window check (its generated name is installation-dependent).
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='promotions'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%starts_minute%' LOOP
  EXECUTE format('ALTER TABLE promotions DROP CONSTRAINT %I',item.conname);
 END LOOP;
END $$;
ALTER TABLE promotions ADD CONSTRAINT promotion_daily_window CHECK(
 (starts_minute IS NULL AND ends_minute IS NULL) OR
 (starts_minute IS NOT NULL AND ends_minute IS NOT NULL AND starts_minute BETWEEN 0 AND 1439 AND ends_minute BETWEEN 1 AND 1440 AND starts_minute<>ends_minute));
