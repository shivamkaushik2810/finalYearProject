-- 08_faculty_absence.sql (Phase 2)
-- Teacher absence records, decisions, audit log, and the initials-to-teacher mapping.
-- Creates NEW objects only. Existing tables are not changed.
-- Security: RLS on every new table, no anon/authenticated policies. Writes go through the
-- two functions below, which the service layer calls with the server-side key.

begin;

create table teacher_codes (
  code text primary key check (code ~ '^[A-Z]{1,4}$'),
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  created_at timestamptz not null default now()
);
create unique index teacher_codes_one_per_teacher on teacher_codes (teacher_id);

create table faculty_absences (
  id bigserial primary key,
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  start_date date not null,
  end_date date not null,
  kind text not null check (kind in ('planned','emergency','unplanned')),
  periods smallint[],
  reason text not null check (char_length(btrim(reason)) between 5 and 500),
  status text not null check (status in ('pending','approved','rejected','cancelled','completed')),
  requested_by text not null,
  approved_by text,
  decision_note text,
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date >= start_date),
  check (periods is null or cardinality(periods) between 1 and 8)
);
create index faculty_absences_teacher_dates on faculty_absences (teacher_id, start_date, end_date);
create index faculty_absences_status on faculty_absences (status);

create table faculty_absence_log (
  id bigserial primary key,
  absence_id bigint not null references faculty_absences(id),
  action text not null,
  from_status text,
  to_status text,
  actor text not null,
  note text,
  at timestamptz not null default now()
);

create or replace function faculty_absence_log_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'faculty_absence_log is append-only';
end $$;

create trigger faculty_absence_log_no_change
  before update or delete on faculty_absence_log
  for each row execute function faculty_absence_log_append_only();

-- Creates an absence. Takes a per-teacher lock so two writers cannot both pass the overlap check.
create or replace function faculty_absence_create(
  p_teacher_id uuid, p_start date, p_end date, p_kind text, p_periods smallint[],
  p_reason text, p_requested_by text, p_status text, p_approved_by text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_id bigint;
  v_clash bigint;
begin
  if p_status not in ('pending','approved') then
    raise exception 'initial status must be pending or approved';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_teacher_id::text, 0));
  select id into v_clash from faculty_absences
   where teacher_id = p_teacher_id
     and status in ('pending','approved')
     and start_date <= p_end and end_date >= p_start
     and (periods is null or p_periods is null or periods && p_periods)
   limit 1;
  if v_clash is not null then
    raise exception 'CLASH: overlaps absence %', v_clash;
  end if;
  insert into faculty_absences (teacher_id, start_date, end_date, kind, periods, reason,
    status, requested_by, approved_by, decided_at)
  values (p_teacher_id, p_start, p_end, p_kind, p_periods, btrim(p_reason),
    p_status, p_requested_by, p_approved_by,
    case when p_status = 'approved' then now() end)
  returning id into v_id;
  insert into faculty_absence_log (absence_id, action, from_status, to_status, actor, note)
  values (v_id, 'create', null, p_status, p_requested_by, null);
  return v_id;
end $$;

-- Decides an absence. Allowed moves: pending to approved or rejected; approved to cancelled.
create or replace function faculty_absence_decide(
  p_id bigint, p_new_status text, p_actor text, p_note text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_status text;
begin
  if p_new_status not in ('approved','rejected','cancelled') then
    raise exception 'unknown decision %', p_new_status;
  end if;
  select status into v_status from faculty_absences where id = p_id for update;
  if not found then
    raise exception 'absence % not found', p_id;
  end if;
  if not ((v_status = 'pending' and p_new_status in ('approved','rejected'))
          or (v_status = 'approved' and p_new_status = 'cancelled')) then
    raise exception 'cannot change an absence from % to %', v_status, p_new_status;
  end if;
  update faculty_absences
     set status = p_new_status,
         approved_by = case when p_new_status = 'approved' then p_actor else approved_by end,
         decision_note = nullif(btrim(p_note), ''),
         decided_at = now(),
         updated_at = now()
   where id = p_id;
  insert into faculty_absence_log (absence_id, action, from_status, to_status, actor, note)
  values (p_id, 'decide', v_status, p_new_status, p_actor, nullif(btrim(p_note), ''));
  return p_id;
end $$;

alter table teacher_codes enable row level security;
alter table faculty_absences enable row level security;
alter table faculty_absence_log enable row level security;

revoke all on teacher_codes, faculty_absences, faculty_absence_log from anon, authenticated;
revoke all on function faculty_absence_create(uuid, date, date, text, smallint[], text, text, text, text)
  from public, anon, authenticated;
revoke all on function faculty_absence_decide(bigint, text, text, text)
  from public, anon, authenticated;
grant execute on function faculty_absence_create(uuid, date, date, text, smallint[], text, text, text, text)
  to service_role;
grant execute on function faculty_absence_decide(bigint, text, text, text) to service_role;

commit;

-- ROLLBACK (manual, new objects only):
-- drop function if exists faculty_absence_create(uuid, date, date, text, smallint[], text, text, text, text);
-- drop function if exists faculty_absence_decide(bigint, text, text, text);
-- drop table if exists faculty_absence_log, faculty_absences, teacher_codes;
-- drop function if exists faculty_absence_log_append_only();
