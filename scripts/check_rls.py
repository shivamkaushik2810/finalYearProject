"""Run after ANY database change: python3 scripts/check_rls.py"""
import sys, tomllib, httpx

s = tomllib.load(open(".streamlit/secrets.toml", "rb"))
url, anon = s["SUPABASE_URL"], s["SUPABASE_KEY"]
H = {"apikey": anon, "Authorization": f"Bearer {anon}"}

# Every table the anon key can see through the API (OpenAPI listing)
spec = httpx.get(f"{url}/rest/v1/", headers=H, timeout=20).json()
tables = sorted(p.strip("/") for p in spec.get("paths", {}) if p != "/" and not p.startswith("/rpc"))
if not tables:   # nothing visible to anon is the best case; fall back to the known list
    tables = ["students", "teachers", "subjects", "subject_students", "attendance_logs",
              "attendance_sessions", "marks", "announcements", "parent_student_links",
              "weekly_reports", "otp_verifications", "model_training_logs"]

exposed = []
for t in tables:
    b = httpx.get(f"{url}/rest/v1/{t}?select=*&limit=1", headers=H, timeout=20).json()
    if isinstance(b, list) and b:
        exposed.append(t)
        print(f"EXPOSED: {t}")
print("All tables locked." if not exposed else f"{len(exposed)} table(s) exposed!")
sys.exit(1 if exposed else 0)
