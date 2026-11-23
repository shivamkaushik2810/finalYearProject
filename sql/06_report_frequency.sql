-- Idempotent. Run once in the Supabase SQL editor.
alter table students add column if not exists report_frequency text not null default 'weekly';
alter table students drop constraint if exists students_report_frequency_check;
alter table students add constraint students_report_frequency_check
  check (report_frequency in ('weekly', 'only_below', 'off'));
-- ROLLBACK: alter table students drop column report_frequency;
