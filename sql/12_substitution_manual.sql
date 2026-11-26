-- 12_substitution_manual.sql (Phase 6)
-- Manual substitute changes, teacher accept and decline, per-class exclusions,
-- an event log, and the consecutive-teaching check. Creates NEW objects only, plus
-- two nullable columns on faculty_substitutions. Existing status values are unchanged.
-- Security: RLS on new tables; anon and authenticated have no access.

begin;

alter table faculty_substitutions add column if not exists accepted_at timestamptz;
alter table faculty_substitutions add column if not exists decided_by text;

create table substitution_exclusions (
  id bigserial primary key,
  version_id bigint not null references timetable_versions(id),
  substitution_date date not null,
  section_code text not null,
  period_no smallint not null check (period_no between 1 and 8),
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  reason text not null,
  created_by text not null,
  created_at timestamptz not null default now(),
  unique (version_id, substitution_date, section_code, period_no, teacher_id)
);

create table faculty_substitution_events (
  id bigserial primary key,
  substitution_id bigint not null references faculty_substitutions(id),
  action text not null check (action in ('confirm','reject','override','accept','decline')),
  from_status text,
  to_status text,
  actor text not null,
  note text,
  at timestamptz not null default now()
);

create or replace function faculty_substitution_events_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'faculty_substitution_events is append-only';
end $$;

create trigger faculty_substitution_events_no_change
  before update or delete on faculty_substitution_events
  for each row execute function faculty_substitution_events_append_only();

-- True if no run of consecutive periods is longer than p_limit. A lunch break ends a run.
create or replace function substitution_run_ok(p_periods smallint[], p_limit smallint, p_lunch_after smallint)
returns boolean
language plpgsql immutable as $$
declare
  p smallint;
  prev smallint := null;
  run int := 0;
begin
  for p in select distinct x from unnest(p_periods) as t(x) order by x loop
    if prev is not null and p = prev + 1 and prev <> p_lunch_after then
      run := run + 1;
    else
      run := 1;
    end if;
    if run > p_limit then
      return false;
    end if;
    prev := p;
  end loop;
  return true;
end $$;

-- Periods a teacher already teaches on a date: permanent timetable plus assigned substitutions,
-- excluding the row being changed.
create or replace function faculty_substitution_teacher_periods(
  p_version_id bigint, p_date date, p_teacher_id uuid, p_exclude_id bigint)
returns smallint[]
language plpgsql security definer set search_path = public as $$
declare
  v_code text;
  v_weekday smallint := extract(isodow from p_date)::smallint;
  v_periods smallint[];
begin
  select code into v_code from teacher_codes where teacher_id = p_teacher_id limit 1;
  select coalesce(array_agg(distinct p order by p), '{}'::smallint[]) into v_periods from (
    select (e.period_no + g)::smallint as p
      from timetable_entries e, generate_series(0, e.block_len - 1) g
     where e.version_id = p_version_id
       and e.weekday = v_weekday
       and e.faculty_code = v_code
       and e.kind in ('theory','lab','training')
    union all
    select s.period_no::smallint
      from faculty_substitutions s
     where s.version_id = p_version_id
       and s.substitution_date = p_date
       and s.substitute_teacher_id = p_teacher_id
       and s.status = 'assigned'
       and s.id <> coalesce(p_exclude_id, -1)
  ) t;
  return v_periods;
end $$;

-- Admin changes the substitute for one class. The old teacher is excluded for that class.
create or replace function faculty_substitution_override(
  p_id bigint, p_teacher_id uuid, p_reason text, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  s faculty_substitutions%rowtype;
  v_new_code text;
  v_periods smallint[];
begin
  if p_reason is null or char_length(btrim(p_reason)) < 5 then
    raise exception 'the reason must be at least 5 characters';
  end if;
  select * into s from faculty_substitutions where id = p_id for update;
  if not found then
    raise exception 'substitution % not found', p_id;
  end if;
  if s.status not in ('proposed','assigned','unassigned') then
    raise exception 'cannot change a % substitution', s.status;
  end if;
  if s.substitute_teacher_id is not distinct from p_teacher_id then
    raise exception 'that teacher is already the substitute for this class';
  end if;
  select code into v_new_code from teacher_codes where teacher_id = p_teacher_id limit 1;
  if v_new_code is null then
    raise exception 'that teacher has no timetable code';
  end if;

  if s.substitute_teacher_id is not null then
    insert into substitution_exclusions (version_id, substitution_date, section_code, period_no,
                                         teacher_id, reason, created_by)
    values (s.version_id, s.substitution_date, s.section_code, s.period_no,
            s.substitute_teacher_id, btrim(p_reason), p_actor)
    on conflict do nothing;
  end if;

  v_periods := faculty_substitution_teacher_periods(s.version_id, s.substitution_date, p_teacher_id, p_id)
               || s.period_no::smallint;
  if not substitution_run_ok(v_periods, 3, 5) then
    raise exception 'CONSECUTIVE: % would teach more than 3 periods in a row', v_new_code;
  end if;

  update faculty_substitutions
     set substitute_teacher_id = p_teacher_id,
         status = 'assigned',
         score = null,
         factors = null,
         reasons = null,
         decided_by = p_actor,
         accepted_at = null
   where id = p_id;

  insert into faculty_substitution_events (substitution_id, action, from_status, to_status, actor, note)
  values (p_id, 'override', s.status, 'assigned', p_actor, btrim(p_reason));
  return p_id;
end $$;

-- The assigned teacher accepts the class. Accepting twice is harmless.
create or replace function faculty_substitution_accept(p_id bigint, p_teacher_id uuid, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  s faculty_substitutions%rowtype;
begin
  select * into s from faculty_substitutions where id = p_id for update;
  if not found then
    raise exception 'substitution % not found', p_id;
  end if;
  if s.substitute_teacher_id is distinct from p_teacher_id or s.status <> 'assigned' then
    raise exception 'not your assignment';
  end if;
  if s.accepted_at is not null then
    return p_id;
  end if;
  update faculty_substitutions set accepted_at = now() where id = p_id;
  insert into faculty_substitution_events (substitution_id, action, from_status, to_status, actor, note)
  values (p_id, 'accept', s.status, s.status, p_actor, null);
  return p_id;
end $$;

-- The assigned teacher declines with a reason. The class becomes unassigned, and that teacher
-- is excluded for this class only.
create or replace function faculty_substitution_decline(
  p_id bigint, p_teacher_id uuid, p_reason text, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  s faculty_substitutions%rowtype;
begin
  if p_reason is null or char_length(btrim(p_reason)) < 5 then
    raise exception 'the reason must be at least 5 characters';
  end if;
  select * into s from faculty_substitutions where id = p_id for update;
  if not found then
    raise exception 'substitution % not found', p_id;
  end if;
  if s.substitute_teacher_id is distinct from p_teacher_id or s.status <> 'assigned' then
    raise exception 'not your assignment';
  end if;

  insert into substitution_exclusions (version_id, substitution_date, section_code, period_no,
                                       teacher_id, reason, created_by)
  values (s.version_id, s.substitution_date, s.section_code, s.period_no,
          p_teacher_id, btrim(p_reason), p_actor)
  on conflict do nothing;

  update faculty_substitutions
     set status = 'unassigned',
         substitute_teacher_id = null,
         score = null,
         factors = null,
         accepted_at = null,
         decided_by = p_actor,
         reasons = 'declined by teacher: ' || btrim(p_reason)
   where id = p_id;

  insert into faculty_substitution_events (substitution_id, action, from_status, to_status, actor, note)
  values (p_id, 'decline', s.status, 'unassigned', p_actor, btrim(p_reason));
  return p_id;
end $$;

alter table substitution_exclusions enable row level security;
alter table faculty_substitution_events enable row level security;

revoke all on substitution_exclusions, faculty_substitution_events from anon, authenticated;
revoke all on function substitution_run_ok(smallint[], smallint, smallint) from public, anon, authenticated;
revoke all on function faculty_substitution_teacher_periods(bigint, date, uuid, bigint) from public, anon, authenticated;
revoke all on function faculty_substitution_override(bigint, uuid, text, text) from public, anon, authenticated;
revoke all on function faculty_substitution_accept(bigint, uuid, text) from public, anon, authenticated;
revoke all on function faculty_substitution_decline(bigint, uuid, text, text) from public, anon, authenticated;
grant execute on function faculty_substitution_override(bigint, uuid, text, text) to service_role;
grant execute on function faculty_substitution_accept(bigint, uuid, text) to service_role;
grant execute on function faculty_substitution_decline(bigint, uuid, text, text) to service_role;

commit;

-- ROLLBACK (manual, new objects only):
-- drop function if exists faculty_substitution_decline(bigint, uuid, text, text);
-- drop function if exists faculty_substitution_accept(bigint, uuid, text);
-- drop function if exists faculty_substitution_override(bigint, uuid, text, text);
-- drop function if exists faculty_substitution_teacher_periods(bigint, date, uuid, bigint);
-- drop function if exists substitution_run_ok(smallint[], smallint, smallint);
-- drop table if exists faculty_substitution_events, substitution_exclusions;
-- drop function if exists faculty_substitution_events_append_only();
-- alter table faculty_substitutions drop column if exists accepted_at, drop column if exists decided_by;
