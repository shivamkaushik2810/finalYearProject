-- Run in Supabase SQL editor. TEST ON A COPY / STAGING FIRST. Run BEFORE deploying the new code.

-- 1) OTP hardening (new code needs created_at + attempts; old plaintext OTPs are discarded)
alter table otp_verifications add column if not exists created_at timestamptz not null default now();
alter table otp_verifications add column if not exists attempts int not null default 0;
delete from otp_verifications;

-- 2) Weekly report dedupe (keeps the newest row of any existing duplicates)
delete from weekly_reports a using weekly_reports b
 where a.student_id = b.student_id and a.subject_id = b.subject_id
   and a.week_start = b.week_start and a.ctid < b.ctid;
create unique index if not exists weekly_reports_student_subject_week_uq
    on weekly_reports (student_id, subject_id, week_start);

-- 3) Marks sanity (rejects out-of-range values at the database level too)
alter table marks drop constraint if exists marks_range_chk;
alter table marks add constraint marks_range_chk
    check (max_marks > 0 and marks_obtained >= 0 and marks_obtained <= max_marks) not valid;
