-- 13_notifications.sql (Phase 7)
-- Durable outbox for substitution notices, plus the in-app inbox. Creates NEW objects only.
-- The unique idempotency key stops the same notice being stored twice, even if the event
-- is processed twice. RLS is on; anon and authenticated have no access.

begin;

create table notification_outbox (
  id bigserial primary key,
  idempotency_key text not null unique,
  recipient_kind text not null check (recipient_kind in ('teacher','admin')),
  recipient_teacher_id uuid references teachers(teacher_id) on delete restrict,
  recipient_email text,
  channel text not null check (channel in ('email','inbox')),
  subject text not null,
  body text not null,
  status text not null default 'pending' check (status in ('pending','sent','failed','skipped')),
  attempts smallint not null default 0 check (attempts >= 0),
  last_error text,
  next_attempt_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  check (channel <> 'email' or recipient_email is not null or status in ('failed','skipped'))
);
create index notification_outbox_due on notification_outbox (status, next_attempt_at);

create table notification_inbox (
  id bigserial primary key,
  teacher_id uuid not null references teachers(teacher_id) on delete restrict,
  subject text not null,
  body text not null,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index notification_inbox_teacher on notification_inbox (teacher_id, read_at);

-- Stores one notice per (event, recipient). A second call with the same key does nothing.
create or replace function notification_enqueue(
  p_key text, p_kind text, p_teacher_id uuid, p_email text, p_subject text, p_body text)
returns boolean
language plpgsql security definer set search_path = public as $$
declare
  v_inserted int;
begin
  insert into notification_outbox (idempotency_key, recipient_kind, recipient_teacher_id,
                                   recipient_email, channel, subject, body)
  values (p_key, p_kind, p_teacher_id, nullif(btrim(p_email), ''), 'email', p_subject, p_body)
  on conflict (idempotency_key) do nothing;
  get diagnostics v_inserted = row_count;
  if p_teacher_id is not null then
    insert into notification_inbox (teacher_id, subject, body)
    select p_teacher_id, p_subject, p_body
     where v_inserted = 1;
  end if;
  return v_inserted = 1;
end $$;

-- Claims a batch of due emails for one worker. Rows are locked, so two workers never take the same row.
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
     set attempts = o.attempts + 1
    from due
   where o.id = due.id
  returning o.*;
end $$;

create or replace function notification_mark(p_id bigint, p_ok boolean, p_error text)
returns void
language plpgsql security definer set search_path = public as $$
begin
  if p_ok then
    update notification_outbox set status = 'sent', sent_at = now(), last_error = null where id = p_id;
  else
    update notification_outbox
       set status = case when attempts >= 5 then 'failed' else 'pending' end,
           last_error = left(p_error, 300),
           next_attempt_at = now() + make_interval(mins => least(60, power(2, attempts)::int))
     where id = p_id;
  end if;
end $$;

alter table notification_outbox enable row level security;
alter table notification_inbox enable row level security;
revoke all on notification_outbox, notification_inbox from anon, authenticated;
revoke all on function notification_enqueue(text, text, uuid, text, text, text) from public, anon, authenticated;
revoke all on function notification_claim(int) from public, anon, authenticated;
revoke all on function notification_mark(bigint, boolean, text) from public, anon, authenticated;
grant execute on function notification_enqueue(text, text, uuid, text, text, text) to service_role;
grant execute on function notification_claim(int) to service_role;
grant execute on function notification_mark(bigint, boolean, text) to service_role;

commit;

-- ROLLBACK (manual, new objects only):
-- drop function if exists notification_enqueue(text, text, uuid, text, text, text);
-- drop function if exists notification_claim(int);
-- drop function if exists notification_mark(bigint, boolean, text);
-- drop table if exists notification_inbox, notification_outbox;
