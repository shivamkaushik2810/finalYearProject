begin;

create or replace function timetable_create_draft(p_source_version_id bigint, p_label text, p_actor text)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    v_new bigint;
    v_src record;
begin
    if p_label is null or length(trim(p_label)) = 0 then
        raise exception 'a name is required for the new draft';
    end if;

    select id, label into v_src from timetable_versions where id = p_source_version_id;
    if not found then
        raise exception 'source version not found';
    end if;

    if exists (select 1 from timetable_versions where label = trim(p_label)) then
        raise exception 'version label already exists';
    end if;

    insert into timetable_versions (label, status, parent_version_id, created_by, notes, created_at, updated_at)
    values (trim(p_label), 'draft', p_source_version_id, p_actor, 'copied from ' || v_src.label, now(), now())
    returning id into v_new;

    insert into timetable_entries
        (version_id, section_id, weekday, period_no, block_len, kind, subject_code, subject_name, faculty_code, room)
    select v_new, section_id, weekday, period_no, block_len, kind, subject_code, subject_name, faculty_code, room
    from timetable_entries
    where version_id = p_source_version_id;

    return v_new;
end $$;

revoke all on function timetable_create_draft(bigint, text, text) from public, anon, authenticated;
grant execute on function timetable_create_draft(bigint, text, text) to service_role;

commit;

-- ROLLBACK: drop function if exists timetable_create_draft(bigint, text, text);
