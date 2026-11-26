-- 15_phase9_claim_lease.sql (Phase 9)
-- Fixes a duplicate-send risk found by the Phase 9 concurrency test. notification_claim used to
-- leave claimed rows due, so a second worker could claim and send the same notice before the
-- first worker marked it. Claiming now sets a 5-minute lease. If a worker crashes between sending
-- and marking, the notice is retried after the lease. That is at-least-once in that rare case,
-- and two live copies are never sent at the same time.

begin;

create or replace function notification_claim(p_limit int)
returns setof notification_outbox
language plpgsql security definer set search_path = public as $$
begin
  return query
  with due as (
    select id from notification_outbox
     where status = 'pending' and channel = 'email' and next_attempt_at <= now()
     order by id
     limit p_limit
     for update skip locked
  )
  update notification_outbox o
     set attempts = o.attempts + 1,
         next_attempt_at = now() + interval '5 minutes'
    from due
   where o.id = due.id
  returning o.*;
end $$;

revoke all on function notification_claim(int) from public, anon, authenticated;
grant execute on function notification_claim(int) to service_role;

commit;
