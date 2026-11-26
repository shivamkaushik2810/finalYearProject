-- 11_substitution_reject.sql (Phase 5)
-- Lets an administrator reject a proposed substitution. Creates one new function only.
-- A rejected class becomes unassigned; it is not deleted, so the record is kept.

begin;

create or replace function faculty_substitution_reject(p_id bigint, p_actor text)
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
    raise exception 'cannot reject a % substitution', v_status;
  end if;
  update faculty_substitutions
     set status = 'unassigned',
         substitute_teacher_id = null,
         score = null,
         reasons = 'rejected by ' || p_actor
   where id = p_id;
  return p_id;
end $$;

revoke all on function faculty_substitution_reject(bigint, text) from public, anon, authenticated;
grant execute on function faculty_substitution_reject(bigint, text) to service_role;

commit;

-- ROLLBACK: drop function if exists faculty_substitution_reject(bigint, text);
