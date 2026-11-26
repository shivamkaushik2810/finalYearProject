-- 10_faculty_substitution.sql (Phase 4)
-- Substitution weights, proposed/assigned/unassigned substitutions, and the functions that save
-- a plan and confirm an assignment. Creates NEW objects only. The permanent timetable is not touched.
-- Security: RLS on every new table; anon and authenticated have no access; functions are service_role only.

begin;

create table substitution_weights (
  criterion text primary key
    check (criterion in ('expertise','workload','department','previous_section','preference')),
  weight smallint not null check (weight between 0 and 100),
  updated_by text not null default 'system',
  updated_at timestamptz not null default now()
);

insert into substitution_weights (criterion, weight) values
  ('expertise', 40), ('workload', 20), ('department', 15), ('previous_section', 15), ('preference', 10)
on conflict (criterion) do nothing;

create table faculty_substitutions (
  id bigserial primary key,
  version_id bigint not null references timetable_versions(id),
  substitution_date date not null,
  weekday smallint not null check (weekday between 1 and 6),
  period_no smallint not null check (period_no between 1 and 8),
  section_code text not null,
  subject_code text not null,
  room text,
  original_teacher_code text not null,
  substitute_teacher_id uuid references teachers(teacher_id) on delete restrict,
  status text not null check (status in ('proposed','assigned','unassigned')),
  score numeric(6,2),
  factors jsonb,
  alternatives jsonb,
  reasons text,
  created_by text not null,
  created_at timestamptz not null default now(),
  check ((status = 'unassigned') = (substitute_teacher_id is null))
);

-- One live row per class period on a date.
create unique index faculty_substitutions_one_per_slot
  on faculty_substitutions (version_id, substitution_date, section_code, period_no)
  where status in ('proposed','assigned','unassigned');

-- A teacher can cover at most one class in a period on a date, once confirmed.
create unique index faculty_substitutions_no_double_booking
  on faculty_substitutions (substitute_teacher_id, substitution_date, period_no)
  where status = 'assigned';

create index faculty_substitutions_date on faculty_substitutions (substitution_date);

create or replace function substitution_weights_set(p_weights jsonb, p_actor text)
returns void
language plpgsql security definer set search_path = public as $$
declare
  k text;
  v_keys int := 0;
  v_total int := 0;
begin
  for k in select jsonb_object_keys(p_weights) loop
    if k not in ('expertise','workload','department','previous_section','preference') then
      raise exception 'unknown criterion %', k;
    end if;
    v_keys := v_keys + 1;
  end loop;
  if v_keys <> 5 then
    raise exception 'all five criteria are required';
  end if;
  select coalesce(sum((value)::int), 0) into v_total from jsonb_each_text(p_weights);
  if v_total <> 100 then
    raise exception 'weights must total 100, got %', v_total;
  end if;
  update substitution_weights w
     set weight = (p_weights ->> w.criterion)::smallint,
         updated_by = p_actor,
         updated_at = now();
end $$;

-- Replaces the proposed and unassigned rows for one date. Rows for slots that already have an
-- assigned substitution are skipped by the unique index, so confirmed work is never overwritten.
create or replace function faculty_substitution_save_plan(
  p_version_id bigint, p_date date, p_rows jsonb, p_actor text)
returns integer
language plpgsql security definer set search_path = public as $$
declare
  v_count integer := 0;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_version_id::text || ':' || p_date::text, 0));
  delete from faculty_substitutions
   where version_id = p_version_id
     and substitution_date = p_date
     and status in ('proposed','unassigned');
  insert into faculty_substitutions (version_id, substitution_date, weekday, period_no, section_code,
    subject_code, room, original_teacher_code, substitute_teacher_id, status, score, factors,
    alternatives, reasons, created_by)
  select p_version_id, p_date, (r->>'weekday')::smallint, (r->>'period')::smallint,
    r->>'section_code', r->>'subject_code', nullif(r->>'room', ''), r->>'absent_code',
    nullif(r->>'substitute_teacher_id', '')::uuid, r->>'status',
    nullif(r->>'score', '')::numeric, r->'factors', r->'alternatives',
    nullif(r->>'reasons', ''), p_actor
  from jsonb_array_elements(p_rows) as r
  on conflict do nothing;
  get diagnostics v_count = row_count;
  return v_count;
end $$;

-- Moves a proposed substitution to assigned. The unique index refuses it if the teacher
-- already covers another class in that period.
create or replace function faculty_substitution_confirm(p_id bigint, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_status text;
begin
  select status into v_status from faculty_substitutions where id = p_id for update;
  if not found then
    raise exception 'substitution % not found', p_id;
  end if;
  if v_status <> 'proposed' then
    raise exception 'cannot confirm a % substitution', v_status;
  end if;
  update faculty_substitutions set status = 'assigned' where id = p_id;
  return p_id;
end $$;

alter table substitution_weights enable row level security;
alter table faculty_substitutions enable row level security;

revoke all on substitution_weights, faculty_substitutions from anon, authenticated;
revoke all on function substitution_weights_set(jsonb, text) from public, anon, authenticated;
revoke all on function faculty_substitution_save_plan(bigint, date, jsonb, text) from public, anon, authenticated;
revoke all on function faculty_substitution_confirm(bigint, text) from public, anon, authenticated;
grant execute on function substitution_weights_set(jsonb, text) to service_role;
grant execute on function faculty_substitution_save_plan(bigint, date, jsonb, text) to service_role;
grant execute on function faculty_substitution_confirm(bigint, text) to service_role;

commit;

-- ROLLBACK (manual, new objects only):
-- drop function if exists substitution_weights_set(jsonb, text);
-- drop function if exists faculty_substitution_save_plan(bigint, date, jsonb, text);
-- drop function if exists faculty_substitution_confirm(bigint, text);
-- drop table if exists faculty_substitutions, substitution_weights;
