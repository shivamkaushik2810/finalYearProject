create index if not exists idx_att_subject_ts          on attendance_logs (subject_id, "timestamp" desc);
create index if not exists idx_att_student_subject_ts  on attendance_logs (student_id, subject_id, "timestamp");
create index if not exists idx_ss_subject              on subject_students (subject_id);
create index if not exists idx_ss_student              on subject_students (student_id);
create index if not exists idx_subjects_teacher        on subjects (teacher_id);
create index if not exists idx_subjects_code           on subjects (subject_code);
create index if not exists idx_subjects_section        on subjects (section);
create index if not exists idx_marks_subject           on marks (subject_id);
create index if not exists idx_marks_student           on marks (student_id);
create index if not exists idx_students_parent         on students (parent_email) where parent_email is not null;
create index if not exists idx_otp_email_purpose       on otp_verifications (email, purpose);

create unique index if not exists uq_weekly_reports
  on weekly_reports (student_id, subject_id, week_start);

create or replace view subject_stats as
select s.subject_id,
       (select count(*) from subject_students ss where ss.subject_id = s.subject_id) as total_students,
       (select count(distinct a."timestamp") from attendance_logs a where a.subject_id = s.subject_id) as total_classes
from subjects s;

create or replace view student_subject_stats as
select student_id, subject_id,
       count(*) as total,
       count(*) filter (where is_present) as present
from attendance_logs
group by student_id, subject_id;
