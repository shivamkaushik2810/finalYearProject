-- Allow the same subject code for different classes (course + year + section).
-- Step A: check for duplicates. This must return zero rows before continuing.
select upper(trim(subject_code)) as code, coalesce(course,'') as course,
       coalesce(year,'') as year, upper(trim(section)) as section, count(*)
from subjects
group by 1,2,3,4
having count(*) > 1;

-- Step B: apply the migration.
begin;

alter table subjects drop constraint if exists subjects_subject_code_key;

create unique index if not exists uq_subjects_code_per_class
  on subjects (
    upper(trim(subject_code)),
    coalesce(course, ''),
    coalesce(year, ''),
    upper(trim(section))
  );

commit;

-- Rollback (only if needed):
-- drop index if exists uq_subjects_code_per_class;
-- alter table subjects add constraint subjects_subject_code_key unique (subject_code);
