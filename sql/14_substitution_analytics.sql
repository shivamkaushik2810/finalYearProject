-- 14_substitution_analytics.sql (Phase 8)
-- Makes confirm and reject write to the event log, so assignment speed and decision rates
-- can be measured. Replaces two functions only. No tables change.

begin;

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
  update faculty_substitutions
     set status = 'assigned', decided_by = p_actor
   where id = p_id;
  insert into faculty_substitution_events (substitution_id, action, from_status, to_status, actor, note)
  values (p_id, 'confirm', 'proposed', 'assigned', p_actor, null);
  return p_id;
end $$;

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
     set status = 'unassigned', substitute_teacher_id = null, score = null,
         reasons = 'rejected by ' || p_actor, decided_by = p_actor
   where id = p_id;
  insert into faculty_substitution_events (substitution_id, action, from_status, to_status, actor, note)
  values (p_id, 'reject', 'proposed', 'unassigned', p_actor, null);
  return p_id;
end $$;

commit;
