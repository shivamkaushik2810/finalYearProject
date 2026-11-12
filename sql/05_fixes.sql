-- Idempotent. Run after sql/04_batch2.sql (re-running is harmless).

-- Fix 1: leave_requests ids as TEXT (no assumption about your id types; no foreign keys needed)
alter table leave_requests alter column student_id type text using student_id::text;
alter table leave_requests alter column subject_id type text using subject_id::text;
alter table leave_requests alter column reviewed_by type text using reviewed_by::text;

-- batch-1 face angles column (04 as first pasted did not include it)
alter table students add column if not exists face_embeddings jsonb default '[]'::jsonb;

-- Fix 2: the aggregate view that the job/eligibility read instead of scanning raw logs
create or replace view student_subject_attendance as
select student_id::text || ':' || subject_id::text as pair_key,
       student_id, subject_id,
       count(*) filter (where is_present or not coalesce(is_excused,false)) as total_classes,
       count(*) filter (where is_present) as present_classes
from attendance_logs group by student_id, subject_id;
revoke all on student_subject_attendance from anon, authenticated;
