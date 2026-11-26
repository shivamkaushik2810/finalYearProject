-- 17_timetable_publish.sql (Publish)
-- Publishes a draft. The previously published version is archived in the same transaction,
-- so the one-published-version rule holds. Creates ONE function. No tables change.

begin;

create or replace function timetable_publish(p_version_id bigint, p_actor text)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_status text;
  v_entries int;
begin
  select status into v_status from timetable_versions where id = p_version_id for update;
  if not found then
    raise exception 'version % not found', p_version_id;
  end if;
  if v_status <> 'draft' then
    raise exception 'only a draft can be published (this is %)', v_status;
  end if;
  select count(*) into v_entries from timetable_entries where version_id = p_version_id;
  if v_entries = 0 then
    raise exception 'an empty timetable cannot be published';
  end if;
  update timetable_versions
     set status = 'archived', notes = coalesce(notes, '') || ' superseded', updated_at = now()
   where status = 'published';
  update timetable_versions
     set status = 'published', approved_by = p_actor, published_at = now(), updated_at = now()
   where id = p_version_id;
  return p_version_id;
end $$;

revoke all on function timetable_publish(bigint, text) from public, anon, authenticated;
grant execute on function timetable_publish(bigint, text) to service_role;

commit;

-- ROLLBACK: drop function if exists timetable_publish(bigint, text);
