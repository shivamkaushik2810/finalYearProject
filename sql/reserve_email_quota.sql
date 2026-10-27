-- Daily email quota guard used by src/services/email_queue.py (_reserve_quota).
-- Returns how many of p_count emails may be sent today (0..p_count).

create table if not exists public.email_quota_usage (
    day  date primary key,
    sent integer not null default 0
);

alter table public.email_quota_usage enable row level security;
-- No policies on purpose: the table is only touched through the function below.

create or replace function public.reserve_email_quota(p_count integer, p_limit integer)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_used    integer;
    v_granted integer;
begin
    if p_count is null or p_count <= 0 then
        return 0;
    end if;

    -- make sure today's row exists, then lock it so concurrent jobs serialize
    insert into public.email_quota_usage (day, sent)
    values (current_date, 0)
    on conflict (day) do nothing;

    select sent into v_used
    from public.email_quota_usage
    where day = current_date
    for update;

    v_granted := greatest(0, least(p_count, p_limit - v_used));

    update public.email_quota_usage
    set sent = sent + v_granted
    where day = current_date;

    return v_granted;
end;
$$;

grant execute on function public.reserve_email_quota(integer, integer) to anon, authenticated;
