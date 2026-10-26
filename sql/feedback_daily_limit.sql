create table if not exists feedback_sent_log (
    sender_role text not null,
    sender_id   text not null,
    sent_day    date not null,
    created_at  timestamptz not null default now(),
    primary key (sender_role, sender_id, sent_day)
);
-- If RLS is enabled on your `feedback` table, give this table the same
-- policies (insert + select + delete for the anon key), or inserts will fail.
