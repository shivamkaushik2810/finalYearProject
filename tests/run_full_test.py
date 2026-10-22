"""Seeds 1 teacher + 100 students, then runs unit, functional, performance, reload and UI tests."""
import sys, os, io, time, json, argparse, statistics, contextlib, urllib.request
from pathlib import Path
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snap_testdata as td          # bootstrap: cwd, sys.path, env

# the weekly runner reads these at import time -> dry run, never sends mail
os.environ.update(DRY_RUN="1", REPORT_WEEK="current",
                  TEST_EMAIL_TO=f"qa@{td.DOMAIN}", TEST_LIMIT="100000")

import numpy as np
from src.database import db
from src.database.config import supabase

ap = argparse.ArgumentParser()
ap.add_argument("--reuse", action="store_true", help="reuse data from the last seeding run")
ap.add_argument("--cleanup", action="store_true", help="delete all test data at the end")
ap.add_argument("--skip-ui", action="store_true", help="skip Streamlit screen tests")
ap.add_argument("--skip-perf", action="store_true", help="skip performance and reload tests")
ap.add_argument("--baseline", action="store_true", help="also time the old per-student query style")
ap.add_argument("--users", type=int, default=8, help="parallel users in the reload test")
ap.add_argument("--reloads", type=int, default=10, help="sequential reloads")
args = ap.parse_args()
SLOW_MS = float(os.getenv("SLOW_MS", "3000"))


class Skip(Exception): pass
class Warn(Exception): pass


RESULTS = []


def run(section, name, fn):
    t0 = time.perf_counter()
    try:
        detail, status = (fn() or ""), "PASS"
    except Skip as e:
        status, detail = "SKIP", str(e)
    except Warn as e:
        status, detail = "WARN", str(e)
    except AssertionError as e:
        status, detail = "FAIL", str(e) or "assertion failed"
    except Exception as e:
        status, detail = "ERROR", f"{type(e).__name__}: {str(e)[:300]}"
    ms = (time.perf_counter() - t0) * 1000
    RESULTS.append({"section": section, "name": name, "status": status, "ms": round(ms), "detail": str(detail)})
    lines = str(detail).splitlines() or [""]
    print(f"  {status:<5} {name}  ({ms:,.0f} ms)" + (f"  - {lines[0]}" if lines[0] else ""))
    for line in lines[1:]:
        print(f"          {line}")


def eq(a, b, msg=""):
    assert a == b, f"{msg} expected {b!r}, got {a!r}".strip()


def pct(vals, p):
    s = sorted(vals)
    return s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))]


def timed(fn, *a, **k):
    t0 = time.perf_counter()
    r = fn(*a, **k)
    return r, (time.perf_counter() - t0) * 1000


def clear(fn):
    getattr(fn, "clear", lambda: None)()


# ───────────────────────── preflight + seeding ─────────────────────────
print("== Preflight")
bad = td.preflight()
if bad:
    print("Missing database objects (run sql/optimize_queries.sql in Supabase first):")
    for b in bad:
        print("  -", b)
    sys.exit(2)
print("  all required tables and views exist")

print("== Seeding (1 teacher, 100 students)")
if args.reuse and td.MANIFEST.exists():
    M = td.load_manifest()
    print(f"  reusing run {M['run_id']}")
else:
    try:
        M = td.seed_all(print)
    except Exception as e:
        print(f"  Seeding failed: {type(e).__name__}: {e}")
        print("  Remove any partial data with: python tests/cleanup_test_data.py")
        sys.exit(1)

T = M["teacher"]
TID = T["teacher_id"]
S1, S2 = M["subjects"]
SUBJ = [S1, S2]
STU = M["students"]
SIDS = [s["student_id"] for s in STU]
ATT = M["attendance"]
truth = {}
for sid, sub, ts, pr in ATT:
    a = truth.setdefault((sid, sub), [0, 0])
    a[0] += 1
    a[1] += 1 if pr else 0
print(f"  teacher login -> username: {T['username']}   password: {T['password']}")


def truth_week(ws, we):
    out = {}
    for sid, sub, ts, pr in ATT:
        if ws <= datetime.fromisoformat(ts).date() <= we:
            a = out.setdefault((sid, sub), [0, 0])
            a[0] += 1
            a[1] += 1 if pr else 0
    return out


# ───────────────────────── UNIT TESTS (no database) ─────────────────────────
def u_week_math():
    from src.services.weekly_report_runner import last_full_week, report_week
    eq(last_full_week(date(2026, 10, 26)), (date(2026, 10, 19), date(2026, 10, 25)), "Monday")
    eq(last_full_week(date(2026, 10, 25)), (date(2026, 10, 12), date(2026, 10, 18)), "Sunday")
    eq(last_full_week(date(2026, 10, 22)), (date(2026, 10, 12), date(2026, 10, 18)), "Thursday")
    eq(report_week("current", date(2026, 10, 22)), (date(2026, 10, 19), date(2026, 10, 22)), "current week")
    eq(db._to_date("2026-10-12T10:00:00"), date(2026, 10, 12), "_to_date")


def u_password_hash():
    h = db.hash_pass("Zx#Probe2026")
    assert db.check_pass("Zx#Probe2026", h) and not db.check_pass("wrong", h)


def u_email_template():
    import src.services.weekly_report_service as wrs
    cap = {}
    orig = wrs._send
    wrs._send = lambda to, subj, html, plain: cap.update(to=to, subj=subj, html=html, plain=plain)
    try:
        wrs.send_weekly_parent_email(
            "Test Parent", "p@x.invalid", "Test Student", "R1", "A",
            [{"subject_name": "Maths", "subject_code": "M1", "total": 5, "attended": 4, "absent": 1, "attendance_pct": 80.0},
             {"subject_name": "Physics", "subject_code": "P1", "total": 4, "attended": 1, "absent": 3, "attendance_pct": 25.0}],
            date(2026, 10, 12), date(2026, 10, 18))
        eq(cap["to"], "p@x.invalid")
        assert "Test Student" in cap["subj"]
        assert "At Risk" in cap["html"] and "Good" in cap["html"], "status labels missing"
        assert "55.6%" in cap["html"], "overall % (5/9) wrong"
        assert "Action Required" in cap["html"], "low-attendance warning missing"
        cap.clear()
        wrs.send_weekly_parent_email(
            "P", "p@x.invalid", "S", "R", "A",
            [{"subject_name": "Maths", "subject_code": "M1", "total": 5, "attended": 5, "absent": 0, "attendance_pct": 100.0}],
            date(2026, 10, 12), date(2026, 10, 18))
        assert "Action Required" not in cap["html"], "warning shown for 100%"
    finally:
        wrs._send = orig


def u_nlp():
    from src.pipelines.nlp_analytics import parse_query, answer_query
    eq(parse_query("Which students are at risk?"), "at_risk")
    eq(parse_query("What is the attendance rate?"), "attendance_rate")
    eq(parse_query("How many students are absent?"), "count_absent")
    studs = [{"student_id": i, "name": n} for i, n in enumerate(["Alpha", "Bravo", "Charlie", "Delta"], 1)]
    logs = ([{"student_id": 1, "is_present": True}] * 4 + [{"student_id": 2, "is_present": True}] * 3 +
            [{"student_id": 2, "is_present": False}] + [{"student_id": 3, "is_present": True}] +
            [{"student_id": 3, "is_present": False}] * 3)
    text, _ = answer_query("which students are at risk", logs, studs, "Maths")
    assert "Charlie" in text and "Bravo" not in text and "Alpha" not in text, text


def u_prediction():
    from src.pipelines.attendance_prediction import predict_absent_risk, get_subject_health
    studs = [{"student_id": i, "name": n} for i, n in enumerate(["Alpha", "Bravo", "Charlie", "Delta"], 1)]
    logs = ([{"student_id": 1, "is_present": True}] * 4 + [{"student_id": 2, "is_present": True}] * 3 +
            [{"student_id": 2, "is_present": False}] + [{"student_id": 3, "is_present": True}] +
            [{"student_id": 3, "is_present": False}] * 3)
    res = {r["name"]: r for r in predict_absent_risk(logs, studs)}
    eq(res["Alpha"]["risk_level"], "low")
    eq(res["Bravo"]["risk_level"], "low")        # exactly 75% is still low risk
    eq(res["Charlie"]["risk_level"], "high")
    eq(res["Delta"]["risk_level"], "unknown")
    mk = lambda p: [{"is_present": i < p} for i in range(10)]
    eq(get_subject_health(mk(9), 10)["status"], "Excellent")
    eq(get_subject_health(mk(6), 10)["status"], "Average")
    eq(get_subject_health(mk(3), 10)["status"], "Poor")


def u_image_quality():
    from src.pipelines.image_quality import check_image_quality, get_image_quality_score, count_faces_in_image
    dark = np.zeros((300, 300, 3), np.uint8)
    ok, warns = check_image_quality(dark)
    assert not ok and len(warns) >= 2, f"dark image not flagged: {warns}"
    noise = np.random.default_rng(1).integers(0, 255, (300, 300, 3), dtype=np.uint8)
    ok, warns = check_image_quality(noise)
    assert ok, f"good image flagged: {warns}"
    assert 0 <= get_image_quality_score(noise) <= 100
    eq(count_faces_in_image(dark), 0, "faces in blank image")


def u_detectors_blank_image():
    from src.pipelines.drowsiness_detection import detect_drowsiness_simple, get_class_drowsiness_summary
    from src.pipelines.emotion_detection import detect_emotions, get_class_emotion_summary
    blank = np.zeros((300, 300, 3), np.uint8)
    eq(detect_drowsiness_simple(blank), [], "drowsiness on blank image")
    eq(get_class_drowsiness_summary([])["total"], 0)
    res, err = detect_emotions(blank)
    assert res == [] and err is None, f"emotion detector: {res} {err}"
    eq(get_class_emotion_summary([]), {})


print("\n== UNIT TESTS")
run("unit", "week boundaries (Mon-Sun logic)", u_week_math)
run("unit", "bcrypt hash/check", u_password_hash)
run("unit", "weekly e-mail template", u_email_template)
run("unit", "NLP intents + answers", u_nlp)
run("unit", "risk prediction + class health", u_prediction)
run("unit", "image quality checks", u_image_quality)
run("unit", "emotion/drowsiness on blank image", u_detectors_blank_image)


# ───────────────────────── FUNCTIONAL TESTS (database) ─────────────────────────
def f_count_students():
    n = len(db._fetch_all(lambda: supabase.table("students").select("student_id").like("email", f"%@{td.DOMAIN}"),
                          order=("student_id",)))
    eq(n, 100, "test students")
    assert db.count_students() >= 100


def f_teacher_login():
    assert db.check_teacher_exists(T["username"])
    row = db.teacher_login(T["username"], T["password"])
    assert row and row["teacher_id"] == TID, "correct password rejected"
    assert db.teacher_login(T["username"], "Wrong#Pass99") is None, "wrong password accepted"


def f_teacher_subjects():
    clear(db.get_teacher_subjects)
    subs = {s["subject_id"]: s for s in db.get_teacher_subjects(TID)}
    for sub in SUBJ:
        row = subs.get(sub["subject_id"])
        assert row, f"{sub['name']} missing"
        eq(row["total_students"], 100, sub["name"] + " students")
        eq(row["total_classes"], len(sub["sessions"]), sub["name"] + " classes")


def f_enrolled_list():
    for sub in SUBJ:
        eq(len(db.get_subject_students_detail(sub["subject_id"])), 100, sub["name"])


def f_student_stats():
    for sub in SUBJ:
        got = db.get_subject_student_stats(sub["subject_id"])
        eq(len(got), 100, "rows")
        bad = [sid for sid in SIDS if list(got.get(sid, (None, None))) != truth[(sid, sub["subject_id"])]]
        assert not bad, f"{sub['name']}: {len(bad)} students differ, e.g. {bad[:2]}"


def f_pagination():
    total = 0
    for sub in SUBJ:
        n = len(db.get_subject_logs(sub["subject_id"]))
        eq(n, len(sub["sessions"]) * 100, sub["name"] + " logs")
        total += n
    n2 = len(db.get_attendance_for_teacher(TID))
    eq(n2, total, "teacher attendance records")
    assert total > 1000, "dataset too small to prove the 1000-row cap is handled"
    return f"{total} rows fetched across pages (cap is 1000)"


def f_student_view():
    sid = SIDS[0]
    clear(db.get_student_subjects)
    clear(db.get_student_attendance)
    eq(len(db.get_student_subjects(sid)), 2, "subjects")
    eq(len(db.get_student_attendance(sid)), sum(len(s["sessions"]) for s in SUBJ), "attendance rows")
    eq(db.get_student_by_id(sid)["roll_no"], STU[0]["roll_no"])
    assert str(sid) in {str(k) for k in db.get_student_names()}
    smap = db.get_enrolled_subjects_map()
    bad = [s for s in SIDS if len(smap.get(s, [])) != 2]
    assert not bad, f"{len(bad)} students without 2 subjects in enrolled map"


def f_embeddings():
    from src.database.students_query import get_students_with_faces
    for s in STU[:5]:
        row = db.get_student_by_id(s["student_id"])
        face = np.array(row["face_embedding"], dtype=float)
        eq(face.shape, (128,), "face dims")
        assert np.allclose(face, M["probe_faces"][str(s["student_id"])], atol=1e-5), "face embedding changed in storage"
        eq(len(row["voice_embedding"]), 256, "voice dims")
    ids = {str(r["student_id"]) for r in get_students_with_faces()}
    assert {str(s) for s in SIDS} <= ids, "get_students_with_faces missed test students"


def f_weekly_bulk():
    from src.services.weekly_report_runner import report_week
    notes = []
    for mode in ("last", "current"):
        ws, we = report_week(mode)
        exp = truth_week(ws, we)
        got = db.get_weekly_attendance_bulk(ws, we)
        bad = [k for k, v in exp.items() if list(got.get(k, (0, 0))) != v]
        assert not bad, f"{mode} week {ws}..{we}: {len(bad)} of {len(exp)} pairs differ"
        notes.append(f"{mode} week {ws}..{we}: {len(exp)} pairs exact")
    return "; ".join(notes)


def _runner(mode):
    os.environ["REPORT_WEEK"] = mode
    from src.services.weekly_report_runner import send_weekly_reports_to_all_parents
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok, failed = send_weekly_reports_to_all_parents(force=True)
    return ok, failed


def f_weekly_runner_dry():
    notes = []
    for mode in ("current", "last"):
        from src.services.weekly_report_runner import report_week
        exp_students = {k[0] for k in truth_week(*report_week(mode))}
        ok, failed = _runner(mode)
        eq(failed, 0, f"{mode}: failures")
        assert ok >= len(exp_students), f"{mode}: only {ok} of {len(exp_students)} test students would be emailed"
        notes.append(f"{mode}: would email {ok} parents (>= {len(exp_students)} test students)")
    return "dry run, nothing sent or saved; " + "; ".join(notes)


def f_weekly_upsert():
    ids5 = SIDS[:5]
    rows = [{"student_id": s, "subject_id": S1["subject_id"], "week_start": "2000-01-03", "week_end": "2000-01-09",
             "total_classes": 5, "attended": 4, "absent": 1, "attendance_pct": 80.0, "email_sent": True} for s in ids5]
    db.save_weekly_reports_bulk(rows)
    db.save_weekly_reports_bulk(rows)          # second call must not duplicate
    cnt = (supabase.table("weekly_reports").select("student_id", count="exact")
           .eq("week_start", "2000-01-03").in_("student_id", ids5).execute().count)
    eq(cnt, 5, "rows after saving twice (is the unique index from optimize_queries.sql applied?)")
    got = {str(x) for x in db.get_reported_student_ids("2000-01-03")}
    assert {str(s) for s in ids5} <= got


def f_marks_counts():
    for sub in SUBJ:
        eq(len(db.get_marks_by_subject(sub["subject_id"])), 300, sub["name"])
    eq(len(db.get_marks_by_student(SIDS[0])), 6, "marks of one student")


def f_marks_crud():
    sid, sub = SIDS[0], S1["subject_id"]
    added = db.add_marks(sid, sub, TID, 17.5, 20, "Practical", "qa")
    mid = added[0]["id"]
    row = [m for m in db.get_marks_by_student(sid) if m["id"] == mid]
    eq(len(row), 1, "added mark")
    db.update_marks(mid, 18, 20, "Practical", "qa2")
    row = [m for m in db.get_marks_by_student(sid) if m["id"] == mid][0]
    eq(float(row["marks_obtained"]), 18.0)
    eq(row["remarks"], "qa2")
    db.delete_marks(mid)
    assert not [m for m in db.get_marks_by_student(sid) if m["id"] == mid], "mark not deleted"


def f_otp():
    from src.services.otp_service import save_otp, verify_otp
    email = f"otp.{M['run_id']}@{td.DOMAIN}"
    save_otp(email, "123456", "student_email")
    ok, _ = verify_otp(email, "000000", "student_email")
    assert not ok, "wrong OTP accepted"
    ok, msg = verify_otp(email, "123456", "student_email")
    assert ok, msg
    ok, _ = verify_otp(email, "123456", "student_email")
    assert not ok, "OTP can be used twice"


def f_parent_lookup():
    a, b = STU[0], STU[1]
    kids = db.get_children_for_parent(a["parent_email"])
    eq({str(k["student_id"]) for k in kids}, {str(a["student_id"]), str(b["student_id"])}, "siblings")
    eq(len(db.get_children_for_parent(a["parent_email"].upper())), 2, "case-insensitive lookup")
    if "parent_student_links" in M["skipped_tables"]:
        raise Skip("parent_student_links table missing: sibling lookup tested only")
    link = M["links"][0]
    kids = db.get_children_for_parent(link["parent_email"])
    assert any(str(k["student_id"]) == str(link["student_id"]) for k in kids), "verified link not honoured"


def f_face_samples_training():
    if "face_samples" in M["skipped_tables"]:
        raise Skip("face_samples table missing")
    n = (supabase.table("face_samples").select("id", count="exact").in_("student_id", SIDS[:20]).execute().count)
    eq(n, 40, "face_samples rows")
    from src.pipelines.self_learning import get_all_training_data
    X, y, w, total = get_all_training_data()
    assert len(X) >= 140 and total >= 100, f"training set too small: {len(X)} samples, {total} students"
    return f"training set: {len(X)} samples from {total} students"


def f_enroll_unenroll_cache():
    sid, sub = SIDS[-1], S2["subject_id"]
    count = lambda: next(s for s in db.get_teacher_subjects(TID) if s["subject_id"] == sub)["total_students"]
    clear(db.get_teacher_subjects)
    eq(count(), 100, "before")
    db.unenroll_student_to_subject(sid, sub)
    eq(count(), 99, "after unenroll (cache not cleared?)")
    db.enroll_student_to_subject(sid, sub)
    eq(count(), 100, "after re-enroll")


def f_create_subject_flow():
    code = f"TST{M['run_id'].upper()}X{int(time.time()) % 100000}"
    kw = dict(subject_code=code, name="QA Lab", section="A", teacher_id=TID)
    try:
        db.create_subject(**kw, course="B.Tech", year="3")
    except TypeError:
        db.create_subject(**kw)
    sub = supabase.table("subjects").select("subject_id").eq("subject_code", code).execute().data[0]["subject_id"]
    picks = SIDS[:3]
    for sid in picks:
        db.enroll_student_to_subject(sid, sub)
    ts = (datetime.now().replace(microsecond=0) - timedelta(seconds=6)).strftime(td.TS)
    db.create_attendance([{"student_id": sid, "subject_id": sub, "timestamp": ts, "is_present": i < 2}
                          for i, sid in enumerate(picks)])
    clear(db.get_teacher_subjects)
    row = next(s for s in db.get_teacher_subjects(TID) if s["subject_id"] == sub)
    eq(row["total_students"], 3, "students")
    eq(row["total_classes"], 1, "classes")
    stats = db.get_subject_student_stats(sub)
    eq(sorted(list(v) for v in stats.values()), [[1, 0], [1, 1], [1, 1]], "per-student stats")
    return "create_subject, enroll, create_attendance and cache refresh OK"


def f_subject_attendance_stats():
    sub = S1["subject_id"]
    got = db.get_subject_attendance_stats(sub)
    eq(len(got), 100, "students in stats")
    bad = [sid for sid in SIDS if [got[sid]["total"], got[sid]["present"]] != truth[(sid, sub)]]
    assert not bad, f"{len(bad)} of 100 students differ from ground truth (first: {got[bad[0]]} vs {truth[(bad[0], sub)]})"
    return "all 100 students match ground truth (test rows carry no excused/cancelled status)"


def f_status_filter():
    try:
        supabase.table("attendance_logs").select("status").limit(1).execute()
    except Exception:
        raise Skip("attendance_logs has no status column")
    from src.services.weekly_report_runner import report_week
    code = f"TST{M['run_id'].upper()}S{int(time.time()) % 100000}"
    kw = dict(subject_code=code, name="QA Status", section="A", teacher_id=TID)
    try:
        db.create_subject(**kw, course="B.Tech", year="3")
    except TypeError:
        db.create_subject(**kw)
    sub = supabase.table("subjects").select("subject_id").eq("subject_code", code).execute().data[0]["subject_id"]
    sid = SIDS[0]
    db.enroll_student_to_subject(sid, sub)
    base = datetime.now().replace(microsecond=0)
    plan = [(True, None), (False, None), (False, "excused"), (False, "cancelled")]
    db.create_attendance([
        {"student_id": sid, "subject_id": sub, "is_present": p, "status": st,
         "timestamp": (base - timedelta(seconds=10 + i)).strftime(td.TS)}
        for i, (p, st) in enumerate(plan)])
    got = db.get_subject_attendance_stats(sub)[sid]
    eq([got["total"], got["present"]], [2, 1], "app stats (eligible)")
    eq(list(db.get_subject_student_stats(sub)[sid]), [2, 1], "view stats (did you run sql/status_views.sql?)")
    eq(list(db.get_weekly_attendance_bulk(*report_week("current"))[(sid, sub)]), [2, 1], "weekly report counts")
    return "excused/cancelled rows are excluded the same way in the app, the views and the weekly report"


def f_full_logs():
    rows = db.get_subject_logs_full(S1["subject_id"])
    eq(len(rows), len(S1["sessions"]) * 100, "rows (the old query stopped at 1000)")
    assert "status" in rows[0], "status column missing"
    return f"{len(rows)} rows, all columns"


def f_marks_filter():
    import inspect
    sub = S1["subject_id"]
    rows = db.get_marks_by_subject(sub)
    assert isinstance(rows, list), f"returns {type(rows).__name__}, expected list"
    eq(len(rows), 300, "marks")
    if "verified_only" in inspect.signature(db.get_marks_by_subject).parameters:
        v = db.get_marks_by_subject(sub, verified_only=True)
        assert isinstance(v, list) and len(v) <= 300
        return f"verified_only returns {len(v)} of 300 test marks"
    return "no verified_only option"


print("\n== FUNCTIONAL TESTS")
for name, fn in [
    ("100 test students stored", f_count_students),
    ("teacher login (right/wrong password)", f_teacher_login),
    ("teacher subjects: students + classes (view)", f_teacher_subjects),
    ("enrolled list (100 per subject)", f_enrolled_list),
    ("per-student stats match ground truth", f_student_stats),
    ("1000-row cap: pagination", f_pagination),
    ("student dashboard data", f_student_view),
    ("face/voice embedding round-trip", f_embeddings),
    ("weekly bulk query exact (last + current week)", f_weekly_bulk),
    ("weekly runner dry run (parents to email)", f_weekly_runner_dry),
    ("weekly report upsert is idempotent", f_weekly_upsert),
    ("marks: counts", f_marks_counts),
    ("marks: add / update / delete", f_marks_crud),
    ("OTP save / verify / reuse", f_otp),
    ("parent lookup (siblings, case, links)", f_parent_lookup),
    ("face_samples + training data load", f_face_samples_training),
    ("enroll/unenroll refreshes cached counts", f_enroll_unenroll_cache),
    ("create subject + enroll + attendance flow", f_create_subject_flow),
    ("admin attendance stats (eligible filter)", f_subject_attendance_stats),
    ("excused/cancelled handled consistently", f_status_filter),
    ("full logs of a subject (no 1000 cap)", f_full_logs),
    ("marks by subject (list, verified_only)", f_marks_filter),
]:
    run("functional", name, fn)


# ───────────────────────── PERFORMANCE + RELOAD ─────────────────────────
def dashboard_load():
    t0 = time.perf_counter()
    db.get_subject_students_detail(S1["subject_id"])
    db.get_subject_student_stats(S1["subject_id"])
    db.get_subject_logs(S1["subject_id"])
    db.get_attendance_for_teacher(TID)
    return (time.perf_counter() - t0) * 1000


def p_latency():
    from src.database.students_query import get_students_with_faces
    from src.services.weekly_report_runner import report_week
    ws, we = report_week("current")
    sid1 = S1["subject_id"]
    cases = [
        ("teacher subjects (view)", lambda: (clear(db.get_teacher_subjects), db.get_teacher_subjects(TID))),
        ("enrolled list, 100 students", lambda: db.get_subject_students_detail(sid1)),
        ("per-student stats (view)", lambda: db.get_subject_student_stats(sid1)),
        ("subject logs, 1200 rows", lambda: db.get_subject_logs(sid1)),
        ("teacher attendance records, 2000+ rows", lambda: db.get_attendance_for_teacher(TID)),
        ("student dashboard (subjects+logs)", lambda: (clear(db.get_student_subjects), clear(db.get_student_attendance),
                                                      db.get_student_subjects(SIDS[0]), db.get_student_attendance(SIDS[0]))),
        ("marks of one subject, 300 rows", lambda: db.get_marks_by_subject(sid1)),
        ("faces for training", get_students_with_faces),
        ("weekly bulk, current week", lambda: db.get_weekly_attendance_bulk(ws, we)),
        ("children of a parent", lambda: db.get_children_for_parent(STU[0]["parent_email"])),
    ]
    lines, slow = [], []
    for label, fn in cases:
        ts = [timed(fn)[1] for _ in range(5)]
        md = statistics.median(ts)
        lines.append(f"{label:<42} min {min(ts):>6.0f}  med {md:>6.0f}  max {max(ts):>6.0f} ms")
        if md > SLOW_MS:
            slow.append(label)
    msg = "\n".join(lines)
    if slow:
        raise Warn(msg + f"\nSLOW (median > {SLOW_MS:.0f} ms): " + ", ".join(slow))
    return msg


def p_cache():
    clear(db.get_teacher_subjects)
    _, cold = timed(db.get_teacher_subjects, TID)
    _, warm = timed(db.get_teacher_subjects, TID)
    assert warm < cold / 2 or warm < 50, f"cache not effective: cold {cold:.0f} ms, warm {warm:.0f} ms"
    return f"cold {cold:.0f} ms -> warm {warm:.1f} ms"


def p_baseline():
    sample = SIDS[:20]
    t0 = time.perf_counter()
    for sid in sample:
        supabase.table("attendance_logs").select("is_present").eq("student_id", sid).eq("subject_id", S1["subject_id"]).execute()
    old = (time.perf_counter() - t0) * 1000 * len(SIDS) / len(sample)
    _, new = timed(db.get_subject_student_stats, S1["subject_id"])
    return f"old per-student queries ~{old:,.0f} ms vs view {new:,.0f} ms ({old / max(new, 1):.0f}x faster)"


def p_face_matching():
    rng = np.random.default_rng(7)
    stored = rng.normal(0, 0.1, (2000, 128))
    idx = rng.choice(2000, 100, replace=False)
    probes = stored[idx] + rng.normal(0, 0.01, (100, 128))
    t0 = time.perf_counter()
    loop = []
    for p in probes:
        d = [np.linalg.norm(s - p) for s in stored]
        loop.append(int(np.argmin(d)))
    loop_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    d2 = (probes ** 2).sum(1)[:, None] - 2 * probes @ stored.T + (stored ** 2).sum(1)[None, :]
    vec = d2.argmin(1)
    vec_ms = (time.perf_counter() - t0) * 1000
    assert list(vec) == list(idx) and loop == list(idx), "nearest-neighbour matching returned wrong students"
    return f"100 probes vs 2000 stored faces: loop {loop_ms:.0f} ms, vectorised {vec_ms:.1f} ms, accuracy 100%"


def r_sequential():
    times, errs = [], []
    for _ in range(args.reloads):
        try:
            times.append(dashboard_load())
        except Exception as e:
            errs.append(str(e)[:80])
    assert not errs, f"{len(errs)} failed reloads: {errs[0]}"
    return f"{len(times)} dashboard reloads: p50 {pct(times, 50):.0f} ms, p95 {pct(times, 95):.0f} ms, max {max(times):.0f} ms"


def r_concurrent():
    def worker(_):
        out, errs = [], []
        for _ in range(5):
            try:
                out.append(dashboard_load())
            except Exception as e:
                errs.append(str(e)[:80])
        return out, errs
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.users) as ex:
        res = list(ex.map(worker, range(args.users)))
    wall = time.perf_counter() - t0
    times = [x for r in res for x in r[0]]
    errs = [e for r in res for e in r[1]]
    assert not errs, f"{len(errs)} failed loads of {args.users * 5}: {errs[0]}"
    return (f"{args.users} users x 5 reloads in {wall:.1f}s ({len(times) / wall:.1f} loads/s), "
            f"p95 {pct(times, 95):.0f} ms, errors 0")


def r_http():
    base = None
    for port in (8501, 8502, 8503):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2).read()
            base = f"http://localhost:{port}"
            break
        except Exception:
            continue
    if not base:
        raise Skip("Streamlit is not running: start it in another terminal and rerun with --reuse")
    times, bad = [], 0
    for _ in range(30):
        t0 = time.perf_counter()
        try:
            r = urllib.request.urlopen(base + "/", timeout=10)
            r.read()
            ok = r.status == 200
        except Exception:
            ok = False
        times.append((time.perf_counter() - t0) * 1000)
        bad += 0 if ok else 1
    assert bad == 0, f"{bad} of 30 page loads failed"
    return f"30 page loads of {base}: p50 {pct(times, 50):.0f} ms, p95 {pct(times, 95):.0f} ms"


if args.skip_perf:
    print("\n== PERFORMANCE / RELOAD skipped (--skip-perf)")
else:
    print("\n== PERFORMANCE")
    run("perf", "query latency (5 runs each)", p_latency)
    run("perf", "cache cold vs warm", p_cache)
    if args.baseline:
        run("perf", "old N+1 style vs view", p_baseline)
    run("perf", "face matching math (synthetic)", p_face_matching)
    print("\n== RELOAD / LOAD")
    run("reload", f"{args.reloads} sequential dashboard reloads", r_sequential)
    run("reload", f"{args.users} concurrent users", r_concurrent)
    run("reload", "HTTP page reload of running app", r_http)


# ───────────────────────── UI TESTS (Streamlit AppTest) ─────────────────────────
def ui_case(session, reruns=1):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(td.ROOT / "app.py"), default_timeout=180)
    at.session_state["model_checked"] = True            # skip auto-retrain (would overwrite model.pkl)
    for k, v in session.items():
        at.session_state[k] = v
    times = []
    for _ in range(reruns):
        t0 = time.perf_counter()
        at.run()
        times.append((time.perf_counter() - t0) * 1000)
        if len(at.exception):
            raise AssertionError("; ".join(str(getattr(e, "value", e))[:160] for e in at.exception))
    return at, times


if args.skip_ui:
    print("\n== UI TESTS skipped (--skip-ui)")
else:
    print("\n== UI TESTS (headless Streamlit)")
    trow = supabase.table("teachers").select("*").eq("teacher_id", TID).execute().data[0]

    def teacher_tab(tab):
        at, t = ui_case({"login_type": "teacher", "teacher_data": trow, "is_logged_in": True,
                         "user_role": "teacher", "current_teacher_tab": tab})
        if len(at.error):
            raise Warn(f"renders, but shows {len(at.error)} error box(es): {str(at.error[0].value)[:120]}")
        return f"renders without errors in {t[0]:.0f} ms"

    for tab in ["take_attendance", "manage_subjects", "enrolled_students", "attendance_records",
                "marks", "ai_insights", "analytics"]:
        run("ui", f"teacher screen: {tab}", lambda tab=tab: teacher_tab(tab))

    def student_screen(sid):
        srow = db.get_student_by_id(sid)
        at, t = ui_case({"login_type": "student", "student_data": srow, "is_logged_in": True, "user_role": "student"})
        return f"{srow['name']}: renders in {t[0]:.0f} ms"

    for sid in (SIDS[0], SIDS[49], SIDS[99]):
        run("ui", f"student dashboard {str(sid)[:8]}", lambda sid=sid: student_screen(sid))

    def ui_reload():
        _, t = ui_case({"login_type": "teacher", "teacher_data": trow, "is_logged_in": True,
                        "user_role": "teacher", "current_teacher_tab": "enrolled_students"}, reruns=8)
        return f"8 reruns: first {t[0]:.0f} ms, then p50 {pct(t[1:], 50):.0f} ms, max {max(t[1:]):.0f} ms"

    run("ui", "reload teacher dashboard 8 times", ui_reload)


# ───────────────────────── REPORT ─────────────────────────
counts = {}
for r in RESULTS:
    counts[r["status"]] = counts.get(r["status"], 0) + 1
print("\n" + "=" * 60)
print("SUMMARY: " + "   ".join(f"{k} {v}" for k, v in sorted(counts.items())))
for r in RESULTS:
    if r["status"] in ("FAIL", "ERROR"):
        print(f"  {r['status']}: [{r['section']}] {r['name']} -> {r['detail'][:200]}")
slow = sorted(RESULTS, key=lambda r: -r["ms"])[:5]
print("Slowest: " + "; ".join(f"{r['name']} {r['ms']:,} ms" for r in slow))

td.RUN_DIR.mkdir(exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
md = [f"# SnapClass test report {stamp}", "", f"Run id: `{M['run_id']}`", "",
      "| Section | Test | Status | ms | Detail |", "|---|---|---|---|---|"]
for r in RESULTS:
    md.append(f"| {r['section']} | {r['name']} | {r['status']} | {r['ms']} | {r['detail'].replace(chr(10), ' / ')[:160]} |")
(td.RUN_DIR / f"report_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
(td.RUN_DIR / f"report_{stamp}.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
print(f"Report saved: test_run/report_{stamp}.md")

if args.cleanup:
    print("\n== Cleanup")
    td.cleanup_test_data(print)
else:
    print("\nTest data is still in the database. Delete it when you are done:")
    print("  python tests/cleanup_test_data.py        (or run the SQL block below in Supabase)")

sys.exit(1 if counts.get("FAIL") or counts.get("ERROR") else 0)
