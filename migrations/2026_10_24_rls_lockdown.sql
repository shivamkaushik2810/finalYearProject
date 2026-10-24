-- DO NOT RUN until SUPABASE_KEY in .streamlit/secrets.toml (and the deployed app's secrets)
-- has been replaced with the SERVICE_ROLE key (Streamlit runs server-side; never expose it).
-- With RLS on and no policies, the public anon key can no longer read or write anything.
-- Test on staging first: the app must still work with the service_role key before you run this.
alter table if exists teachers              enable row level security;
alter table if exists students              enable row level security;
alter table if exists subjects              enable row level security;
alter table if exists subject_students      enable row level security;
alter table if exists attendance_logs       enable row level security;
alter table if exists attendance_sessions   enable row level security;
alter table if exists marks                 enable row level security;
alter table if exists weekly_reports        enable row level security;
alter table if exists otp_verifications     enable row level security;
alter table if exists model_training_logs   enable row level security;
alter table if exists announcements         enable row level security;
alter table if exists parent_student_links  enable row level security;
-- Also drop the existing "allow all" policies on these tables (Dashboard > Auth > Policies).
