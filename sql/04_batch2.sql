-- columns
alter table students add column if not exists phone text;
alter table students add column if not exists parent_phone text;
alter table students add column if not exists alert_opt_in boolean default false;
alter table attendance_logs add column if not exists is_excused boolean default false;

-- leave requests (created in batch 1; safe if already present)
create table if not exists leave_requests (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null, subject_id uuid not null,
  kind text not null default 'leave' check (kind in ('leave','medical')),
  start_date date not null, end_date date not null, reason text not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  reviewed_by uuid, review_note text, reviewed_at timestamptz,
  created_at timestamptz default now(), check (end_date >= start_date)
);
alter table leave_requests add column if not exists document_path text;
alter table leave_requests enable row level security;

-- private bucket for medical certificates
insert into storage.buckets (id, name, public) values ('leave-docs','leave-docs',false)
on conflict (id) do nothing;

-- fast aggregate (excused absences are not counted against the student)
create or replace view student_subject_attendance as
select student_id::text || ':' || subject_id::text as pair_key,
       student_id, subject_id,
       count(*) filter (where is_present or not coalesce(is_excused,false)) as total_classes,
       count(*) filter (where is_present) as present_classes
from attendance_logs group by student_id, subject_id;
revoke all on student_subject_attendance from anon, authenticated;

-- audit log (append-only)
create table if not exists attendance_audit_log (
  id bigserial primary key, log_id text not null, student_id text, subject_id text,
  changed_by text not null, old_value boolean, new_value boolean,
  reason text not null, changed_at timestamptz not null default now()
);
create or replace function audit_log_immutable() returns trigger language plpgsql as $$
begin raise exception 'attendance_audit_log is append-only'; end $$;
drop trigger if exists audit_no_change on attendance_audit_log;
create trigger audit_no_change before update or delete on attendance_audit_log
  for each row execute function audit_log_immutable();
alter table attendance_audit_log enable row level security;

-- atomic correction: ownership check + update + audit in one transaction
create or replace function correct_attendance(
  p_log_id text, p_teacher_id text, p_new_present boolean, p_reason text)
returns json language plpgsql security definer set search_path = public as $$
declare v_log record; v_old boolean;
begin
  if p_reason is null or length(trim(p_reason)) < 5 then
    raise exception 'Reason must be at least 5 characters'; end if;
  select l.* into v_log from attendance_logs l
    join subjects s on s.subject_id = l.subject_id
   where l.id::text = p_log_id and s.teacher_id::text = p_teacher_id
   for update of l;
  if not found then raise exception 'Record not found or not your subject'; end if;
  v_old := coalesce(v_log.is_present, false);
  if v_old = p_new_present then raise exception 'No change: status already set'; end if;
  update attendance_logs
     set is_present = p_new_present,
         is_excused = case when p_new_present then false else is_excused end
   where id = v_log.id;
  insert into attendance_audit_log(log_id, student_id, subject_id, changed_by, old_value, new_value, reason)
  values (p_log_id, v_log.student_id::text, v_log.subject_id::text, p_teacher_id, v_old, p_new_present, trim(p_reason));
  return json_build_object('ok', true);
end $$;
revoke all on function correct_attendance(text,text,boolean,text) from public, anon, authenticated;
grant execute on function correct_attendance(text,text,boolean,text) to service_role;

-- eligibility
create table if not exists eligibility_settings (
  subject_id text primary key,
  eligible_min numeric not null default 75,
  condonable_min numeric not null default 65,
  updated_by text, updated_at timestamptz default now(),
  check (condonable_min > 0 and condonable_min <= eligible_min and eligible_min <= 100)
);
create table if not exists condonation_decisions (
  subject_id text not null, student_id text not null,
  decision text not null check (decision in ('condoned','denied')),
  reason text not null, decided_by text not null, decided_at timestamptz default now(),
  primary key (subject_id, student_id)
);

-- alerts (unique key prevents duplicate notifications)
create table if not exists alert_log (
  id bigserial primary key, student_id text not null, kind text not null,
  channel text not null, period_key text not null, status text not null default 'pending',
  created_at timestamptz default now(),
  unique (student_id, kind, channel, period_key)
);

-- timetable slots and geofence
create table if not exists subject_slots (
  id bigserial primary key, subject_id text not null,
  weekday smallint not null check (weekday between 0 and 6),
  start_time time not null, end_time time not null,
  grace_minutes int not null default 10 check (grace_minutes between 0 and 60),
  check (end_time > start_time)
);
create index if not exists subject_slots_idx on subject_slots (subject_id, weekday);
create table if not exists subject_geofence (
  subject_id text primary key, enabled boolean not null default false,
  latitude double precision check (latitude between -90 and 90),
  longitude double precision check (longitude between -180 and 180),
  radius_m int not null default 100 check (radius_m between 20 and 2000),
  allowed_ips text[] not null default '{}',
  updated_by text, updated_at timestamptz default now()
);

-- new tables must be locked down too
alter table eligibility_settings enable row level security;
alter table condonation_decisions enable row level security;
alter table alert_log enable row level security;
alter table subject_slots enable row level security;
alter table subject_geofence enable row level security;

-- ROLLBACK (manual): drop the tables/views/functions above; columns can stay.
