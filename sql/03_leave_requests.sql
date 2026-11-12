create table if not exists leave_requests (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null,
  subject_id uuid not null,
  kind text not null default 'leave' check (kind in ('leave','medical')),
  start_date date not null,
  end_date date not null,
  reason text not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  reviewed_by uuid,
  review_note text,
  reviewed_at timestamptz,
  created_at timestamptz default now(),
  check (end_date >= start_date)
);
create index if not exists leave_requests_subject_idx on leave_requests (subject_id, status);
create index if not exists leave_requests_student_idx on leave_requests (student_id);
alter table leave_requests enable row level security;
alter table attendance_logs add column if not exists is_excused boolean default false;
