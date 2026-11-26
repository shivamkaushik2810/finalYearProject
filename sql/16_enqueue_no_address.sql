-- 16_enqueue_no_address.sql (Phase 9)
-- A notice with no email address is stored as 'failed' at once, with a reason, instead of
-- violating the outbox check. This matches the designed behaviour: the admin sees the failure.
-- Replaces one function only. No tables change.

begin;

create or replace function notification_enqueue(
  p_key text, p_kind text, p_teacher_id uuid, p_email text, p_subject text, p_body text)
returns boolean
language plpgsql security definer set search_path = public as $$
declare
  v_inserted int;
  v_addr text := nullif(btrim(p_email), '');
begin
  insert into notification_outbox (idempotency_key, recipient_kind, recipient_teacher_id,
                                   recipient_email, channel, subject, body, status, last_error)
  values (p_key, p_kind, p_teacher_id, v_addr, 'email', p_subject, p_body,
          case when v_addr is null then 'failed' else 'pending' end,
          case when v_addr is null then 'no email address on file' else null end)
  on conflict (idempotency_key) do nothing;
  get diagnostics v_inserted = row_count;
  if p_teacher_id is not null then
    insert into notification_inbox (teacher_id, subject, body)
    select p_teacher_id, p_subject, p_body
     where v_inserted = 1;
  end if;
  return v_inserted = 1;
end $$;

revoke all on function notification_enqueue(text, text, uuid, text, text, text) from public, anon, authenticated;
grant execute on function notification_enqueue(text, text, uuid, text, text, text) to service_role;

commit;
