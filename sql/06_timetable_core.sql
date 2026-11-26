-- 06_timetable_core.sql (Phase A)
-- Creates NEW tables only. Existing timetables and subject_slots are not changed or deleted.
-- Run once in the Supabase SQL editor. Plain CREATE statements fail if a name already exists.
-- Security: RLS is enabled on every new table with no anon/authenticated policies. The app uses the
-- server-side service key, so admin-only edits and published-only reads are enforced in the service layer.

begin;

create table academic_years (
  id bigserial primary key,
  code smallint not null unique check (code between 1 and 4),
  label text not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

create table sections (
  id bigserial primary key,
  year_code smallint not null references academic_years(code),
  code text not null unique,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  check (
    (year_code = 1 and code ~ '^[PC][1-4]$')
    or (year_code between 2 and 4 and code ~ '^[2-4][A-Z]$' and left(code, 1) = year_code::text)
  )
);

create table timetable_settings (
  id bigserial primary key,
  name text not null unique,
  working_days smallint[] not null default '{1,2,3,4,5,6}',
  periods_per_day smallint not null default 8 check (periods_per_day between 1 and 12),
  lecture_minutes smallint not null default 50 check (lecture_minutes between 30 and 90),
  lunch_after_period smallint not null default 5,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  check (cardinality(working_days) between 1 and 7),
  check (lunch_after_period between 0 and periods_per_day)
);

create table period_slots (
  period_no smallint primary key check (period_no between 1 and 12),
  start_time time not null,
  end_time time not null,
  check (end_time > start_time)
);

create table timetable_versions (
  id bigserial primary key,
  label text not null unique,
  status text not null default 'draft'
    check (status in ('draft','under_review','approved','published','archived')),
  parent_version_id bigint references timetable_versions(id),
  created_by text,
  approved_by text,
  published_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index one_published_version on timetable_versions (status) where status = 'published';

create table timetable_entries (
  id bigserial primary key,
  version_id bigint not null references timetable_versions(id),
  section_id bigint not null references sections(id),
  weekday smallint not null check (weekday between 1 and 7),
  period_no smallint not null references period_slots(period_no),
  block_len smallint not null default 1 check (block_len between 1 and 4),
  kind text not null check (kind in ('theory','lab','training','activity')),
  subject_code text,
  subject_name text,
  faculty_code text,
  room text,
  created_at timestamptz not null default now(),
  unique (version_id, section_id, weekday, period_no)
);
create index tt_entries_version_section on timetable_entries (version_id, section_id);
create index tt_entries_version_faculty on timetable_entries (version_id, faculty_code);
create index tt_entries_version_room on timetable_entries (version_id, room);

create table timetable_changes (
  id bigserial primary key,
  version_id bigint not null references timetable_versions(id),
  entry_id bigint,
  action text not null check (action in ('insert','update','delete','import')),
  before_json jsonb,
  after_json jsonb,
  changed_by text not null,
  changed_at timestamptz not null default now()
);

-- Published and archived versions cannot be edited. Create a new draft instead.
create or replace function timetable_entries_guard() returns trigger
language plpgsql as $$
declare
  v_id bigint;
  v_status text;
begin
  if tg_op = 'DELETE' then v_id := old.version_id; else v_id := new.version_id; end if;
  select status into v_status from timetable_versions where id = v_id;
  if v_status in ('published', 'archived') then
    raise exception 'Version % is % and cannot be changed; create a new draft', v_id, v_status;
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

drop trigger if exists timetable_entries_guard_trg on timetable_entries;
create trigger timetable_entries_guard_trg
  before insert or update or delete on timetable_entries
  for each row execute function timetable_entries_guard();

-- The change log is append-only.
create or replace function timetable_changes_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'timetable_changes is append-only';
end $$;

drop trigger if exists timetable_changes_no_update on timetable_changes;
create trigger timetable_changes_no_update
  before update or delete on timetable_changes
  for each row execute function timetable_changes_append_only();

-- Seed data. Lunch is not a row; it sits after period 5.
insert into academic_years (code, label, is_active) values
  (1, 'First Year', true), (2, 'Second Year', true), (3, 'Third Year', true), (4, 'Fourth Year', false)
on conflict (code) do nothing;

insert into sections (year_code, code) values
  (1,'P1'),(1,'P2'),(1,'P3'),(1,'P4'),(1,'C1'),(1,'C2'),(1,'C3'),(1,'C4'),
  (2,'2A'),(2,'2B'),(2,'2C'),(2,'2D'),(2,'2E'),(2,'2F'),
  (3,'3A'),(3,'3B'),(3,'3C'),(3,'3D'),(3,'3E'),(3,'3F')
on conflict (code) do nothing;

insert into period_slots (period_no, start_time, end_time) values
  (1,'09:00','10:00'), (2,'10:00','10:50'), (3,'11:00','11:50'), (4,'11:50','12:40'),
  (5,'12:40','13:30'), (6,'14:20','15:10'), (7,'15:10','16:00'), (8,'16:00','16:55')
on conflict (period_no) do nothing;

insert into timetable_settings (name) values ('default') on conflict (name) do nothing;

alter table academic_years enable row level security;
alter table sections enable row level security;
alter table timetable_settings enable row level security;
alter table period_slots enable row level security;
alter table timetable_versions enable row level security;
alter table timetable_entries enable row level security;
alter table timetable_changes enable row level security;

-- Read-only compatibility view over the EXISTING timetables table.
-- If this line errors, delete the create view and revoke lines, run the rest, and report the error.
-- Legacy day_of_week is 0 = Monday; the new weekday is 1 = Monday.
create view timetable_legacy_view as
select t.id as legacy_id, t.subject_id, t.day_of_week, t.start_time, t.end_time, t.room,
       s.name as subject_name, s.subject_code, s.section
from timetables t
left join subjects s on s.subject_id = t.subject_id;
revoke all on timetable_legacy_view from anon, authenticated;

commit;

-- ROLLBACK (manual, new objects only):
-- drop view if exists timetable_legacy_view;
-- drop table if exists timetable_changes, timetable_entries, timetable_versions,
--   period_slots, timetable_settings, sections, academic_years cascade;
-- drop function if exists timetable_entries_guard(), timetable_changes_append_only();
