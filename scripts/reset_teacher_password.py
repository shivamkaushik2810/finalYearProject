"""
List teachers:     python scripts/reset_teacher_password.py
Reset a password:  python scripts/reset_teacher_password.py <username> <new_password>
"""
import sys, tomllib, bcrypt
from supabase import create_client

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)
sb = create_client(secrets["SUPABASE_URL"], secrets["SUPABASE_KEY"])

if len(sys.argv) == 1:
    rows = sb.table("teachers").select("username, name, email").execute().data or []
    if not rows:
        print("No teachers registered yet.")
    for r in rows:
        print(f"username={r['username']}  name={r['name']}  email={r.get('email')}")
    sys.exit()

username, new_pass = sys.argv[1], sys.argv[2]
hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
res = sb.table("teachers").update({"password": hashed}).eq("username", username).execute()
print("Password updated." if res.data else f"No teacher found with username '{username}'.")
