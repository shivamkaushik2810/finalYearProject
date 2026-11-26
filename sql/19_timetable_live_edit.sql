begin;

-- 1. Edits are allowed on the live (published) version only.
create or replace function apply_timetable_change(p_entry_id bigint, p_expected jsonb, p_new jsonb, p_actor text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $function$
declare
  v_version_id bigint;
  v_status text;
  v_old timetable_entries%rowtype;
  v_new timetable_entries%rowtype;
  v_key text;
  v_clash text;
  c_editable constant text[] := array['weekday','period_no','block_len','kind',
                                      'subject_code','subject_name','faculty_code','room'];
begin
  if p_new is null or jsonb_typeof(p_new) <> 'object' then
    raise exception 'changes must be an object';
  end if;
  for v_key in select jsonb_object_keys(p_new) loop
    if not (v_key = any (c_editable)) then
      raise exception 'field % is not editable', v_key;
    end if;
  end loop;

  select version_id into v_version_id from timetable_entries where id = p_entry_id;
  if not found then
    raise exception 'entry % not found', p_entry_id;
  end if;

  -- Serialise all edits to this version.
  select status into v_status from timetable_versions where id = v_version_id for update;
  if v_status <> 'published' then
    raise exception 'version is %, only the live timetable can be edited', v_status;
  end if;

  select * into v_old from timetable_entries where id = p_entry_id for update;

  for v_key in select jsonb_object_keys(p_expected) loop
    if (to_jsonb(v_old) ->> v_key) is distinct from (p_expected ->> v_key) then
      raise exception 'CONFLICT: entry changed since it was loaded (%)', v_key;
    end if;
  end loop;

  v_new := jsonb_populate_record(v_old, p_new);

  select string_agg(format('clash with entry %s on day %s period %s',
                           o.id, o.weekday, o.period_no), '; ')
    into v_clash
  from timetable_entries o
  where o.version_id = v_version_id
    and o.id <> p_entry_id
    and o.weekday = v_new.weekday
    and o.period_no < v_new.period_no + v_new.block_len
    and v_new.period_no < o.period_no + o.block_len
    and (o.section_id = v_new.section_id
         or (v_new.kind in ('theory','lab','training') and o.kind in ('theory','lab','training')
             and o.faculty_code = v_new.faculty_code)
         or (v_new.room is not null and o.room = v_new.room));
  if v_clash is not null then
    raise exception 'CLASH: %', v_clash;
  end if;

  update timetable_entries set
    weekday = v_new.weekday, period_no = v_new.period_no, block_len = v_new.block_len,
    kind = v_new.kind, subject_code = v_new.subject_code, subject_name = v_new.subject_name,
    faculty_code = v_new.faculty_code, room = v_new.room
  where id = p_entry_id;

  insert into timetable_changes (version_id, entry_id, action, before_json, after_json, changed_by)
  values (v_version_id, p_entry_id, 'update', to_jsonb(v_old), to_jsonb(v_new), p_actor);

  return jsonb_build_object('ok', true, 'entry_id', p_entry_id, 'version_id', v_version_id);
end $function$;

-- 2. The guard: live entries may be edited (updated) but not added or removed,
--    and archived versions stay locked.
create or replace function timetable_entries_guard()
returns trigger
language plpgsql
as $$
declare
  v_id bigint;
  v_status text;
begin
  if tg_op = 'DELETE' then v_id := old.version_id; else v_id := new.version_id; end if;
  select status into v_status from timetable_versions where id = v_id;
  if v_status = 'archived' then
    raise exception 'Version % is archived and cannot be changed', v_id;
  end if;
  if v_status = 'published' and tg_op <> 'UPDATE' then
    raise exception 'Version % is live: entries can be edited, not added or removed', v_id;
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

commit;

-- ROLLBACK: re-run the previous definitions. In apply_timetable_change, change
-- "if v_status <> 'published'" back to "if v_status <> 'draft'" (and its message).
-- The old guard raised for any change when status was published or archived.
