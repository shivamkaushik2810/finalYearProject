"""
Create (or reset) a demo teacher login. Run: python scripts/create_demo_teacher.py
Password satisfies the app's rules (8-16 chars, upper, lower, digit, symbol,
no dictionary words).
"""
import tomllib, bcrypt
from supabase import create_client

USERNAME = "demoprof"
PASSWORD = "Demo@Class2026"
NAME     = "Demo Professor"

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)
sb = create_client(secrets["SUPABASE_URL"], secrets["SUPABASE_KEY"])

hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
existing = sb.table("teachers").select("username").eq("username", USERNAME).execute().data

if existing:
    sb.table("teachers").update({"password": hashed, "name": NAME}).eq("username", USERNAME).execute()
    print("Demo teacher already existed - password reset.")
else:
    sb.table("teachers").insert({
        "username": USERNAME, "password": hashed, "name": NAME, "email": None
    }).execute()
    print("Demo teacher created.")

print(f"\nLogin ->  username: {USERNAME}   password: {PASSWORD}")
