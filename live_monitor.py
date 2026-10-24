import os
import smtplib
import ssl
import subprocess
import time
import tomllib
from datetime import datetime

from supabase import create_client

INTERVAL = 10        # seconds between refreshes
SMTP_EVERY = 60      # Gmail login check interval (don't hammer Gmail)

with open(".streamlit/secrets.toml", "rb") as f:
    S = tomllib.load(f)
sb = create_client(S["SUPABASE_URL"], S["SUPABASE_KEY"])

smtp_state = ("not checked yet", 0)
last_smtp = 0


def streamlit_running():
    r = subprocess.run(["pgrep", "-f", "streamlit run"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def timed(fn):
    t = time.time()
    try:
        v = fn()
        return True, round((time.time() - t) * 1000), v
    except Exception as e:
        return False, round((time.time() - t) * 1000), str(e)[:80]


def count(table):
    return sb.table(table).select("*", count="exact").limit(1).execute().count


def latest_session():
    rows = (sb.table("attendance_logs").select("timestamp,is_present")
            .order("timestamp", desc=True).limit(200).execute().data or [])
    if not rows:
        return "no sessions yet"
    ts = rows[0]["timestamp"]
    same = [r for r in rows if r["timestamp"] == ts]
    pres = sum(1 for r in same if r["is_present"])
    return f"{ts}  ({pres} present / {len(same)})"


def check_smtp():
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as srv:
            srv.starttls(context=ssl.create_default_context())
            srv.login(S["EMAIL_ADDRESS"], S["EMAIL_PASSWORD"].replace(" ", ""))
        return "OK"
    except Exception as e:
        return f"FAILED: {type(e).__name__}"


def tail(path, n=4):
    if not os.path.exists(path):
        return ["(file not found)"]
    with open(path, errors="ignore") as f:
        return [l.rstrip() for l in f.readlines()[-n:]] or ["(empty)"]


def mark(ok):
    return "🟢" if ok else "🔴"


while True:
    try:
        now = time.time()
        if now - last_smtp > SMTP_EVERY:
            smtp_state = (check_smtp(), datetime.now().strftime("%H:%M:%S"))
            last_smtp = now

        os.system("clear")
        print(f"SnapClass live monitor   {datetime.now():%d %b %Y %H:%M:%S}   (Ctrl+C to quit)\n")

        run = streamlit_running()
        print(f"{mark(run)} Streamlit process : {'running' if run else 'NOT running'}")

        ok, ms, v = timed(lambda: count("students"))
        print(f"{mark(ok)} Supabase          : {f'{ms} ms' if ok else v}")
        if ok:
            print(f"   students          : {v}")
            for t in ("teachers", "subjects", "attendance_logs", "weekly_reports"):
                ok2, _, v2 = timed(lambda t=t: count(t))
                print(f"   {t:<17} : {v2 if ok2 else 'error: ' + v2}")
            ok3, _, v3 = timed(latest_session)
            print(f"   latest session    : {v3}")

        good = smtp_state[0] == "OK"
        print(f"\n{mark(good)} Gmail login       : {smtp_state[0]} (checked {smtp_state[1]})")

        for name in ("learning_log.txt", "face_debug.log", "app.log"):
            print(f"\n--- {name} (last lines) ---")
            for line in tail(name):
                print(line[:150])

        time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")
        break
