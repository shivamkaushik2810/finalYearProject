-- 09_faculty_planning.sql (Phase 3)
-- Subject qualifications, standing unavailability, and workload limits per teacher.
-- Creates NEW objects only. Writes go through the functions below, which write the audit
-- row in the same transaction. RLS is on for every new table; anon and authenticated have no access.

begin;

create table faculty_subject_qualifications (
  id bigserial primary key,
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  subject_code text not null check (char_length(btrim(subject_code)) between 1 and 40),
  level text not null check (level in ('trained','primary','secondary')),
  is_active boolean not null default true,
  updated_by text not null,
  updated_at timestamptz not null default now(),
  unique (teacher_id, subject_code)
);

create table faculty_unavailability (
  id bigserial primary key,
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  weekday smallint not null check (weekday between 1 and 6),
  period_no smallint check (period_no between 1 and 8),
  reason text not null check (char_length(btrim(reason)) between 3 and 200),
  effective_from date not null,
  effective_until date,
  created_by text not null,
  created_at timestamptz not null default now(),
  check (effective_until is null or effective_until >= effective_from)
);
create index faculty_unavailability_teacher_day on faculty_unavailability (teacher_id, weekday);

create table faculty_limits (
  teacher_id uuid primary key references teachers(teacher_id) on delete restrict,
  max_daily_periods smallint not null check (max_daily_periods between 0 and 8),
  max_weekly_periods smallint not null check (max_weekly_periods between 0 and 48),
  updated_by text not null,
  updated_at timestamptz not null default now(),
  check (max_daily_periods <= max_weekly_periods)
);

create table faculty_planning_log (
  id bigserial primary key,
  teacher_id uuid not null,
  entity text not null check (entity in ('qualification','unavailability','limits')),
  action text not null,
  detail jsonb not null,
  actor text not null,
  at timestamptz not null default now()
);

create or replace function faculty_planning_log_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'faculty_planning_log is append-only';
end $$;

create trigger faculty_planning_log_no_change
  before update or delete on faculty_planning_log
  for each row execute function faculty_planning_log_append_only();

create or replace function faculty_qualification_set(
  p_teacher_id uuid, p_subject_code text, p_level text, p_active boolean, p_actor text)
returns void
language plpgsql security definer set search_path = public as $$
declare
  v_old text;
  v_code text := btrim(p_subject_code);
begin
  if p_level not in ('trained','primary','secondary') then
    raise exception 'unknown level %', p_level;
  end if;
  select level into v_old from faculty_subject_qualifications
   where teacher_id = p_teacher_id and subject_code = v_code;
  insert into faculty_subject_qualifications (teacher_id, subject_code, level, is_active, updated_by, updated_at)
  values (p_teacher_id, v_code, p_level, p_active, p_actor, now())
  on conflict (teacher_id, subject_code)
  do update set level = excluded.level, is_active = excluded.is_active,
                updated_by = excluded.updated_by, updated_at = now();
  insert into faculty_planning_log (teacher_id, entity, action, detail, actor)
  values (p_teacher_id, 'qualification', 'set',
          jsonb_build_object('subject_code', v_code, 'old_level', v_old,
                             'new_level', p_level, 'active', p_active), p_actor);
end $$;

create or replace function faculty_unavailability_add(
  p_teacher_id uuid, p_weekday smallint, p_period smallint, p_reason text,
  p_from date, p_until date, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_id bigint;
begin
  insert into faculty_unavailability (teacher_id, weekday, period_no, reason,
                                      effective_from, effective_until, created_by)
  values (p_teacher_id, p_weekday, p_period, btrim(p_reason), p_from, p_until, p_actor)
  returning id into v_id;
  insert into faculty_planning_log (teacher_id, entity, action, detail, actor)
  values (p_teacher_id, 'unavailability', 'add',
          jsonb_build_object('id', v_id, 'weekday', p_weekday, 'period', p_period,
                             'from', p_from, 'until', p_until), p_actor);
  return v_id;
end $$;

create or replace function faculty_limits_set(
  p_teacher_id uuid, p_max_daily smallint, p_max_weekly smallint, p_actor text)
returns void
language plpgsql security definer set search_path = public as $$
begin
  insert into faculty_limits (teacher_id, max_daily_periods, max_weekly_periods, updated_by, updated_at)
  values (p_teacher_id, p_max_daily, p_max_weekly, p_actor, now())
  on conflict (teacher_id)
  do update set max_daily_periods = excluded.max_daily_periods,
                max_weekly_periods = excluded.max_weekly_periods,
                updated_by = excluded.updated_by, updated_at = now();
  insert into faculty_planning_log (teacher_id, entity, action, detail, actor)
  values (p_teacher_id, 'limits', 'set',
          jsonb_build_object('max_daily', p_max_daily, 'max_weekly', p_max_weekly), p_actor);
end $$;

alter table faculty_subject_qualifications enable row level security;
alter table faculty_unavailability enable row level security;
alter table faculty_limits enable row level security;
alter table faculty_planning_log enable row level security;

revoke all on faculty_subject_qualifications, faculty_unavailability,
  faculty_limits, faculty_planning_log from anon, authenticated;
revoke all on function faculty_qualification_set(uuid, text, text, boolean, text) from public, anon, authenticated;
revoke all on function faculty_unavailability_add(uuid, smallint, smallint, text, date, date, text) from public, anon, authenticated;
revoke all on function faculty_limits_set(uuid, smallint, smallint, text) from public, anon, authenticated;
grant execute on function faculty_qualification_set(uuid, text, text, boolean, text) to service_role;
grant execute on function faculty_unavailability_add(uuid, smallint, smallint, text, date, date, text) to service_role;
grant execute on function faculty_limits_set(uuid, smallint, smallint, text) to service_role;

commit;

-- ROLLBACK (manual, new objects only):
-- drop function if exists faculty_qualification_set(uuid, text, text, boolean, text);
-- drop function if exists faculty_unavailability_add(uuid, smallint, smallint, text, date, date, text);
-- drop function if exists faculty_limits_set(uuid, smallint, smallint, text);
-- drop table if exists faculty_planning_log, faculty_limits, faculty_unavailability, faculty_subject_qualifications;
-- drop function if exists faculty_planning_log_append_only();
