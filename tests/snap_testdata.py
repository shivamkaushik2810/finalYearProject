"""QA helpers: bootstrap, seeding (1 teacher + 100 fully populated students) and cleanup."""
import os, sys, re, json, time, random, secrets, string
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import bcrypt
from src.database.config import supabase
from src.database import db

DOMAIN = "snapclass-test.invalid"
TS = "%Y-%m-%dT%H:%M:%S"
RUN_DIR = ROOT / "test_run"
MANIFEST = RUN_DIR / "manifest.json"
_DROPPED = {}

REQUIRED = ["teachers", "students", "subjects", "subject_students", "attendance_logs", "marks",
            "weekly_reports", "otp_verifications", "subject_stats", "student_subject_stats"]

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Rahul", "Ishaan", "Kabir", "Dev",
         "Siddharth", "Yash", "Harsh", "Nikhil", "Ankit", "Priya", "Ananya", "Diya", "Isha", "Kavya",
         "Meera", "Neha", "Pooja", "Riya", "Sneha", "Shreya", "Tanvi", "Aditi", "Nisha", "Simran",
         "Mohit", "Varun", "Tushar", "Gaurav", "Mansi", "Anjali", "Divya", "Kritika", "Sakshi", "Palak"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Yadav", "Mishra", "Jain", "Agarwal", "Chauhan",
        "Tiwari", "Pandey", "Saxena", "Rastogi", "Tyagi", "Malik", "Bansal", "Goel", "Mehta", "Joshi"]
PARENT_FIRST = ["Rajesh", "Sunil", "Anil", "Manoj", "Vijay", "Sanjay", "Ramesh", "Suresh", "Deepak",
                "Ashok", "Pradeep", "Mukesh"]
EXAMS = [("Internal", 30), ("Mid Term", 50), ("End Term", 100)]
STUDENT_COLS = ["name", "email", "roll_no", "section", "year", "course", "parent_name",
                "parent_email", "face_embedding", "voice_embedding"]


# ───────────────────────── generic helpers ─────────────────────────
def safe_insert(table, rows, chunk=500):
    """Insert rows; if the table lacks a column we sent, drop that column and retry."""
    rows = [dict(r) for r in rows]
    out = []
    for i in range(0, len(rows), chunk):
        part = [{k: v for k, v in r.items() if k not in _DROPPED.get(table, ())}
                for r in rows[i:i + chunk]]
        for _ in range(15):
            try:
                out.extend(supabase.table(table).insert(part).execute().data or [])
                break
            except Exception as e:
                m = re.search(r"Could not find the '([^']+)' column", str(e))
                if not m:
                    raise
                _DROPPED.setdefault(table, set()).add(m.group(1))
                part = [{k: v for k, v in r.items() if k != m.group(1)} for r in part]
        else:
            raise RuntimeError(f"too many unknown columns for {table}")
    return out


def _is_missing_table(e):
    s = str(e)
    return "PGRST205" in s or "schema cache" in s or "does not exist" in s


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def preflight():
    bad = []
    for t in REQUIRED:
        try:
            supabase.table(t).select("*").limit(1).execute()
        except Exception as e:
            bad.append(f"{t}: {str(e)[:80]}")
    return bad


def gen_password():
    up = "".join(secrets.choice(string.ascii_uppercase) for _ in range(3))
    lo = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
    return f"{up}{lo}{secrets.randbelow(90) + 10}#x"   # 10 chars, upper+lower+digit+symbol


# ───────────────────────── data generation ─────────────────────────
def make_students(n, run_id, seed=2026):
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    used, out = set(), []
    for i in range(1, n + 1):
        sibling = i <= 10 and i % 2 == 0           # students 1-10 form 5 sibling pairs (shared parent)
        last = out[-1]["_last"] if sibling else rng.choice(LAST)
        for _ in range(200):
            first = rng.choice(FIRST)
            if (first, last) not in used:
                break
        used.add((first, last))
        if sibling:
            parent_name, fam = out[-1]["parent_name"], out[-1]["_fam"]
        else:
            parent_name, fam = f"{rng.choice(PARENT_FIRST)} {last}", f"{i:03d}"
        r = rng.random()
        if r < 0.70:
            p, tier = rng.uniform(0.85, 0.98), "good"
        elif r < 0.90:
            p, tier = rng.uniform(0.60, 0.80), "average"
        else:
            p, tier = rng.uniform(0.20, 0.50), "poor"
        face = nrng.normal(0, 0.1, 128).round(6).tolist()                 # dlib-style 128-d
        v = nrng.normal(0, 1, 256)
        voice = (v / np.linalg.norm(v)).round(6).tolist()                 # resemblyzer-style 256-d
        out.append({
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}.{i:03d}.{run_id}@{DOMAIN}",
            "roll_no": f"TST{run_id[:2].upper()}{i:03d}",
            "section": "A", "year": "3", "course": "B.Tech",
            "parent_name": parent_name,
            "parent_email": f"parent{fam}.{run_id}@{DOMAIN}",
            "face_embedding": face, "voice_embedding": voice,
            "_last": last, "_fam": fam, "_p": p, "_tier": tier,
        })
    return out


def make_sessions(n, now, offset_s, hour, minute):
    """First session = now (so 'this week' reports have data), the rest on earlier weekdays."""
    times = [now - timedelta(seconds=offset_s)]
    d = now.date()
    while len(times) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            times.append(datetime(d.year, d.month, d.day, hour, minute, 0))
    return times


def make_attendance(students, subject_id, times, rng):
    rows = []
    for t in times:
        ts = t.strftime(TS)
        for s in students:
            present = rng.random() < s["_p"]
            rows.append({"student_id": s["student_id"], "subject_id": subject_id, "timestamp": ts,
                         "is_present": present,
                         "confidence_score": round(rng.uniform(0.72, 0.99), 2) if present else None})
    return rows


def make_marks(students, subject_id, teacher_id, rng):
    rows = []
    for s in students:
        for exam, mx in EXAMS:
            frac = max(0.0, min(1.0, 0.35 + 0.6 * s["_p"] + rng.uniform(-0.08, 0.08)))
            remarks = "Good progress" if frac >= 0.75 else ("Needs improvement" if frac < 0.5 else "Satisfactory")
            rows.append({"student_id": s["student_id"], "subject_id": subject_id, "teacher_id": teacher_id,
                         "marks_obtained": round(frac * mx, 1), "max_marks": mx,
                         "exam_type": exam, "remarks": remarks})
    return rows


# ───────────────────────── seeding ─────────────────────────
def seed_all(log=print, n_students=100, ml_sessions=12, db_sessions=8):
    timings = {}

    def step(name, fn):
        t0 = time.perf_counter()
        r = fn()
        timings[name] = round((time.perf_counter() - t0) * 1000)
        log(f"  seeded {name:<24} {timings[name]:>7,} ms")
        return r

    run_id = secrets.token_hex(3)
    rng = random.Random(2026)
    now = datetime.now().replace(microsecond=0)
    pwd = gen_password()
    skipped = []

    teacher = step("teacher", lambda: safe_insert("teachers", [{
        "username": f"tst_{run_id}",
        "password": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        "name": "Dr. Meera Iyer", "email": f"tst.teacher.{run_id}@{DOMAIN}", "status": "approved"}])[0])
    tid = teacher["teacher_id"]

    code_ml, code_db = f"TST{run_id.upper()}ML", f"TST{run_id.upper()}DB"
    subs = step("subjects", lambda: safe_insert("subjects", [
        {"subject_code": code_ml, "name": "Machine Learning", "section": "A",
         "teacher_id": tid, "course": "B.Tech", "year": "3"},
        {"subject_code": code_db, "name": "Database Systems", "section": "A",
         "teacher_id": tid, "course": "B.Tech", "year": "3"}]))
    by_code = {s["subject_code"]: s["subject_id"] for s in subs}
    ml_id, db_id = by_code[code_ml], by_code[code_db]

    students = make_students(n_students, run_id)
    inserted = step("students+embeddings", lambda: safe_insert(
        "students", [{k: s[k] for k in STUDENT_COLS} for s in students], chunk=50))
    by_roll = {r["roll_no"]: r["student_id"] for r in inserted}
    for s in students:
        s["student_id"] = by_roll[s["roll_no"]]

    step("enrollments", lambda: safe_insert("subject_students", [
        {"student_id": s["student_id"], "subject_id": sub} for s in students for sub in (ml_id, db_id)]))

    ml_times = make_sessions(ml_sessions, now, 0, 10, 0)
    db_times = make_sessions(db_sessions, now, 2, 11, 30)
    att = make_attendance(students, ml_id, ml_times, rng) + make_attendance(students, db_id, db_times, rng)
    step("attendance_logs", lambda: safe_insert("attendance_logs", att))

    marks = make_marks(students, ml_id, tid, rng) + make_marks(students, db_id, tid, rng)
    step("marks", lambda: safe_insert("marks", marks))

    links = [{"student_id": s["student_id"], "parent_email": f"guardian{i:03d}.{run_id}@{DOMAIN}",
              "is_verified": True} for i, s in enumerate(students[10:15], start=11)]
    nrng = np.random.default_rng(99)
    samples = []
    for s in students[:20]:
        for _ in range(2):
            emb = (np.array(s["face_embedding"]) + nrng.normal(0, 0.01, 128)).round(6).tolist()
            samples.append({"student_id": s["student_id"], "embedding": emb,
                            "confidence": round(rng.uniform(0.7, 0.95), 2), "source": "attendance"})
    for table, rows in (("parent_student_links", links), ("face_samples", samples)):
        try:
            step(table, lambda t=table, r=rows: safe_insert(t, r))
        except Exception as e:
            if _is_missing_table(e):
                skipped.append(table)
                log(f"  skipped {table} (table missing)")
            else:
                raise

    manifest = {
        "run_id": run_id, "created_at": now.isoformat(), "domain": DOMAIN,
        "teacher": {"teacher_id": tid, "username": f"tst_{run_id}", "password": pwd,
                    "email": f"tst.teacher.{run_id}@{DOMAIN}", "name": "Dr. Meera Iyer"},
        "subjects": [
            {"subject_id": ml_id, "subject_code": code_ml, "name": "Machine Learning",
             "sessions": [t.strftime(TS) for t in ml_times]},
            {"subject_id": db_id, "subject_code": code_db, "name": "Database Systems",
             "sessions": [t.strftime(TS) for t in db_times]}],
        "students": [{"student_id": s["student_id"], "name": s["name"], "email": s["email"],
                      "roll_no": s["roll_no"], "parent_email": s["parent_email"],
                      "tier": s["_tier"], "p": round(s["_p"], 3)} for s in students],
        "attendance": [[a["student_id"], a["subject_id"], a["timestamp"], bool(a["is_present"])] for a in att],
        "links": [{"student_id": l["student_id"], "parent_email": l["parent_email"]} for l in links],
        "probe_faces": {str(s["student_id"]): s["face_embedding"] for s in students[:5]},
        "timings_ms": timings, "skipped_tables": skipped,
        "dropped_columns": {t: sorted(c) for t, c in _DROPPED.items()},
    }
    RUN_DIR.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, default=str), encoding="utf-8")
    return manifest


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ───────────────────────── cleanup ─────────────────────────
def _ids(col, builder):
    return [r[col] for r in db._fetch_all(builder, order=(col,))]


def find_test_ids():
    stu = _ids("student_id", lambda: supabase.table("students").select("student_id").like("email", f"%@{DOMAIN}"))
    tea = _ids("teacher_id", lambda: supabase.table("teachers").select("teacher_id").like("email", f"%@{DOMAIN}"))
    sub = set(_ids("subject_id", lambda: supabase.table("subjects").select("subject_id").like("subject_code", "TST%")))
    for c in _chunks(tea, 50):
        sub |= set(_ids("subject_id", lambda c=c: supabase.table("subjects").select("subject_id").in_("teacher_id", c)))
    return stu, tea, sorted(sub, key=str)


def count_test_rows():
    stu, tea, sub = find_test_ids()
    n_att = 0
    for c in _chunks(sub, 50):
        n_att += supabase.table("attendance_logs").select("student_id", count="exact").in_("subject_id", c).limit(1).execute().count or 0
    return {"students": len(stu), "teachers": len(tea), "subjects": len(sub), "attendance_rows": n_att}


def _delete_in(table, col, ids, log):
    if not ids:
        return
    for c in _chunks(ids, 50):
        try:
            supabase.table(table).delete().in_(col, c).execute()
        except Exception as e:
            if _is_missing_table(e):
                return                           # table does not exist in this project
            raise
    log(f"  cleared {table}.{col}  ({len(ids)} ids)")


def cleanup_test_data(log=print):
    stu, tea, sub = find_test_ids()
    log(f"Found test data: {len(stu)} students, {len(tea)} teachers, {len(sub)} subjects")
    for table in ("weekly_reports", "attendance_logs", "marks", "subject_students", "face_samples",
                  "parent_student_links", "attendance_scans"):
        _delete_in(table, "student_id", stu, log)
    for table in ("attendance_logs", "marks", "weekly_reports", "subject_students",
                  "attendance_sessions", "attendance_scans", "timetables"):
        _delete_in(table, "subject_id", sub, log)
    _delete_in("subjects", "subject_id", sub, log)
    _delete_in("students", "student_id", stu, log)
    _delete_in("teachers", "teacher_id", tea, log)
    for table in ("otp_verifications", "parent_student_links"):
        col = "email" if table == "otp_verifications" else "parent_email"
        try:
            supabase.table(table).delete().like(col, f"%@{DOMAIN}").execute()
        except Exception as e:
            if not _is_missing_table(e):
                raise
    for f in (ROOT / "model.pkl", MANIFEST):
        if f.exists():
            f.unlink()
            log(f"  removed {f.name}")
    left = count_test_rows()
    log(f"Remaining test rows: {left}")
    real = supabase.table("students").select("student_id", count="exact").limit(1).execute().count
    log(f"Real students still in the database: {real}")
    return left
