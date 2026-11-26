"""Creates test teacher accounts (one per section) for manual QA.
Marker: username starts with tst_ and email ends with @snapclass-test.invalid.
Run: python scripts/create_test_teachers.py
"""
import os, secrets, string, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

from src.database.config import supabase
from src.database.db import hash_pass

SECTIONS = ["1C", "1D", "2A", "2B", "2C", "2D", "2E", "2F", "3A", "3B", "3C", "3D", "3E", "3F"]
RUN = secrets.token_hex(2)

def gen_password():
    pool = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(10)) + "#"
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw

rows = []
for sec in SECTIONS:
    rows.append({
        "username": f"tst_{RUN}_{sec.lower()}",
        "name": f"Test Teacher {sec}",
        "email": f"tst.{RUN}.{sec.lower()}@snapclass-test.invalid",
        "status": "approved",
    })

print(f"Run id: {RUN}")
for r in rows:
    pw = gen_password()
    supabase.table("teachers").insert({
        **r,
        "password": hash_pass(pw),
    }).execute()
    print(f"{r['username']}  password: {pw}  section-tag: {r['name'][-2:]}")
