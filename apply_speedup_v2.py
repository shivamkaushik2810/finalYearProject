import ast
import os
import re
import shutil
import sys

if not os.path.exists("src/pipelines/face_pipeline.py"):
    sys.exit("Run this from the project root (folder with app.py and src/).")

RESULTS = []


def say(status, msg):
    RESULTS.append(status)
    print(f"  [{status}] {msg}")


def load(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def save(p, text):
    """Syntax-check, back up once, then write. Returns (ok, error)."""
    try:
        ast.parse(text)
    except SyntaxError as e:
        return False, f"would create a syntax error: {e}"
    if os.path.exists(p) and not os.path.exists(p + ".speedup.bak"):
        shutil.copy(p, p + ".speedup.bak")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return True, ""


def add_import(path, line):
    t = load(path)
    if line in t:
        return say("skip", f"{path}: import already present")
    m = re.search(r"^(?:import|from)\s", t, re.M)
    if not m:
        return say("FAIL", f"{path}: no import line found")
    ok, err = save(path, t[:m.start()] + line + "\n" + t[m.start():])
    say("ok" if ok else "FAIL", f"{path}: added import ({err})" if not ok else f"{path}: added import")


def replace_function(path, name, new_code, skip_if=None, refuse_if=None, need_sig=None):
    t = load(path)
    pat = re.compile(rf"^def {name}\(.*?(?=^(?:def |class |@)|\Z)", re.M | re.S)
    m = pat.search(t)
    if not m:
        return say("FAIL", f"{path}: function {name}() not found")
    body = m.group(0)
    if skip_if and re.search(skip_if, body):
        return say("skip", f"{path}: {name}() already optimized")
    if refuse_if and re.search(refuse_if, body):
        return say("SKIP-MANUAL", f"{path}: {name}() looks customized ({refuse_if}); not touching it")
    if need_sig:
        sig = re.search(rf"^def {need_sig[0]}\((.*?)\)\s*:", t, re.M | re.S)
        if not sig or not all(n in sig.group(1) for n in need_sig[1]):
            return say("SKIP-MANUAL", f"{path}: {need_sig[0]}() signature differs; not touching {name}()")
    tail = t[m.end():]
    new_text = t[:m.start()] + new_code.strip() + ("\n\n\n" if tail.strip() else "\n") + tail
    ok, err = save(path, new_text)
    say("ok" if ok else "FAIL", f"{path}: replaced {name}()" if ok else f"{path}: {name}() {err}")


def write_new(path, text):
    ok, err = save(path, text)
    say("ok" if ok else "FAIL", f"created {path}" if ok else f"{path}: {err}")


# ---------------- NEW FILES ----------------
FACE_INDEX = r'''import numpy as np
import streamlit as st
from src.database.db import get_all_students


@st.cache_resource(ttl=300)
def get_face_index():
    """Load all embeddings ONCE into a matrix + dict. Cached for 5 minutes."""
    students = get_all_students()
    ids, embs, by_id = [], [], {}
    for s in students:
        by_id[s['student_id']] = s
        if s.get('face_embedding'):
            ids.append(s['student_id'])
            embs.append(s['face_embedding'])
    matrix = (np.asarray(embs, dtype=np.float32)
              if embs else np.empty((0, 128), dtype=np.float32))
    return {"ids": ids, "matrix": matrix, "students": by_id}


def invalidate_face_index():
    """Call after a new student registers."""
    get_face_index.clear()


def nearest_student(encoding, threshold=0.45):
    """Vectorized nearest neighbour. Returns (student_id | None, distance)."""
    idx = get_face_index()
    if not idx["ids"]:
        return None, None
    dists = np.linalg.norm(
        idx["matrix"] - np.asarray(encoding, dtype=np.float32), axis=1
    )
    i = int(np.argmin(dists))
    d = float(dists[i])
    return (idx["ids"][i], d) if d < threshold else (None, d)
'''

WEEKLY_DATA = r'''from collections import defaultdict
from datetime import timedelta
from src.database.config import supabase


def _fetch_all(query_builder, page=1000):
    """Supabase returns max 1000 rows per call, so page through results."""
    rows, start = [], 0
    while True:
        chunk = query_builder.range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def get_week_stats(week_start, week_end):
    """{(student_id, subject_id): {"total": n, "attended": n}} in ONE query."""
    end_exclusive = week_end + timedelta(days=1)  # include all of Sunday
    q = (supabase.table('attendance_logs')
         .select('student_id, subject_id, is_present')
         .gte('timestamp', str(week_start))
         .lt('timestamp', str(end_exclusive)))
    stats = defaultdict(lambda: {"total": 0, "attended": 0})
    for r in _fetch_all(q):
        key = (r['student_id'], r['subject_id'])
        stats[key]["total"] += 1
        if r.get('is_present'):
            stats[key]["attended"] += 1
    return stats


def get_enrollments_map():
    """{student_id: [subject dict, ...]} in ONE query."""
    q = supabase.table('subject_students').select(
        'student_id, subjects(subject_id, name, subject_code)')
    m = defaultdict(list)
    for r in _fetch_all(q):
        if r.get('subjects'):
            m[r['student_id']].append(r['subjects'])
    return m
'''

# ---------------- REPLACEMENT FUNCTIONS ----------------
PREDICT = r'''def predict_attendance(image_np):
    """Returns (detected_dict, all_ids, num_faces). Uses cached matrix lookup."""
    detected, all_ids, num_faces = {}, [], 0
    threshold = globals().get("THRESHOLD", 0.45)
    try:
        locations = face_recognition.face_locations(image_np, model='hog')
        num_faces = len(locations)
        if num_faces == 0:
            return detected, all_ids, num_faces
        encodings = face_recognition.face_encodings(image_np, locations, num_jitters=3)
        for enc in encodings:
            sid, dist = nearest_student(enc, threshold)
            if sid is not None:
                detected[sid] = True
                all_ids.append(sid)
                print(f"Detected {sid} (dist={dist:.3f})")
    except Exception as e:
        print(f"Prediction error: {e}")
    return detected, all_ids, num_faces
'''

PARENTS = r'''def get_all_enrolled_students_with_parents():
    """Get all students who have parent emails for weekly reports"""
    response = supabase.table('students')\
        .select('*')\
        .not_.is_('parent_email', 'null')\
        .execute()
    return response.data
'''

WEEKLY_MAIN = r'''def send_weekly_reports_to_all_parents():
    """Send weekly reports to all parents. Call every Monday."""
    today      = date.today()
    week_end   = today - timedelta(days=1)
    week_start = week_end - timedelta(days=6)

    print(f"Sending weekly reports for {week_start} to {week_end}")

    students    = get_all_enrolled_students_with_parents()
    stats       = get_week_stats(week_start, week_end)   # 1 query
    enrollments = get_enrollments_map()                  # 1 query
    success, failed = 0, 0

    for student in students:
        try:
            student_id   = student['student_id']
            parent_email = student.get('parent_email')
            parent_name  = student.get('parent_name') or 'Parent'
            if not parent_email:
                continue

            subjects = enrollments.get(student_id, [])
            if not subjects:
                continue

            subject_reports = []
            for sub in subjects:
                s = stats.get((student_id, sub['subject_id']),
                              {"total": 0, "attended": 0})
                total, attended = s["total"], s["attended"]
                absent = total - attended
                pct = round((attended / total) * 100, 1) if total > 0 else 0

                subject_reports.append({
                    'subject_name':   sub['name'],
                    'subject_code':   sub['subject_code'],
                    'total':          total,
                    'attended':       attended,
                    'absent':         absent,
                    'attendance_pct': pct
                })
                save_weekly_report(student_id, sub['subject_id'],
                                   week_start, week_end,
                                   total, attended, absent, pct)

            send_weekly_parent_email(
                parent_name=parent_name, parent_email=parent_email,
                student_name=student['name'],
                roll_no=student.get('roll_no', 'N/A'),
                section=student.get('section', 'N/A'),
                subject_reports=subject_reports,
                week_start=week_start, week_end=week_end
            )
            success += 1
            print(f"  Sent to parent of {student['name']}")

        except Exception as e:
            failed += 1
            print(f"  Failed for {student.get('name', 'Unknown')}: {e}")

    print(f"\nDone! Success: {success}, Failed: {failed}")
    return success, failed
'''

ENROLLED_TAB = r'''def teacher_tab_enrolled_students():
    """Show enrolled students list for each subject"""
    from collections import defaultdict
    from src.database.config import supabase

    teacher_id = st.session_state.teacher_data['teacher_id']
    subjects   = get_teacher_subjects(teacher_id)

    st.header("👥 Enrolled Students")

    if not subjects:
        st.info("No subjects created yet. Create a subject first.")
        return

    subject_options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    selected_label  = st.selectbox("Select Subject", list(subject_options.keys()), key='enroll_list_sub')

    if selected_label:
        selected_sub = subject_options[selected_label]
        sid          = selected_sub['subject_id']

        res = supabase.table('subject_students').select('*, students(student_id, name, email, roll_no, section, parent_email)').eq('subject_id', sid).execute()
        enrolled = [n['students'] for n in (res.data or []) if n.get('students')]

        # ONE query for all attendance, grouped: student_id -> [present, total]
        att = defaultdict(lambda: [0, 0])
        att_rows = supabase.table('attendance_logs').select('student_id, is_present').eq('subject_id', sid).execute().data or []
        for l in att_rows:
            att[l['student_id']][1] += 1
            if l.get('is_present'):
                att[l['student_id']][0] += 1

        st.divider()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Enrolled", len(enrolled))
        with col2:
            st.metric("With Email", sum(1 for s in enrolled if s.get('email')))
        with col3:
            st.metric("With Parent Email", sum(1 for s in enrolled if s.get('parent_email')))

        st.divider()

        if not enrolled:
            st.warning("No students enrolled in this subject yet.")
            return

        st.subheader(f"📋 Student List — {selected_sub['name']} ({selected_sub['subject_code']})")

        search = st.text_input("🔍 Search student", placeholder="Type name or roll no...")

        filtered = enrolled
        if search:
            q = search.lower()
            filtered = [s for s in enrolled if
                        q in (s.get('name') or '').lower() or
                        q in (s.get('roll_no') or '').lower()]

        for i, student in enumerate(filtered):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                with c1:
                    st.write(f"**{i+1}. {student.get('name', 'Unknown')}**")
                    st.caption(f"Roll No: {student.get('roll_no', 'N/A')} | Section: {student.get('section', 'N/A')}")
                with c2:
                    st.write(f"📧 {student.get('email') or 'No email'}")
                with c3:
                    st.write(f"👨‍👩‍👧 {student.get('parent_email') or 'No parent email'}")
                with c4:
                    present, total = att[student['student_id']]
                    pct   = round((present / total) * 100) if total > 0 else 0
                    color = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"
                    st.write(f"{color} {present}/{total} ({pct}%)")
'''

# ---------------- RUN ----------------
print("1) New files")
write_new("src/pipelines/face_index.py", FACE_INDEX)
write_new("src/services/weekly_data.py", WEEKLY_DATA)

print("2) face_pipeline.py")
FP = "src/pipelines/face_pipeline.py"
add_import(FP, "from src.pipelines.face_index import nearest_student")
replace_function(FP, "predict_attendance", PREDICT,
                 skip_if=r"nearest_student\(", refuse_if=r"(?i)yolo")

print("3) student_screen.py")
SS = "src/screens/student_screen.py"
add_import(SS, "from src.pipelines.face_index import invalidate_face_index")
t = load(SS)
if "invalidate_face_index()" in t:
    say("skip", f"{SS}: invalidate call already present")
elif re.search(r"^\s*train_classifier\(\)\s*$", t, re.M):
    t = re.sub(r"^(\s*)train_classifier\(\)[ \t]*$",
               r"\1train_classifier()\n\1invalidate_face_index()", t, flags=re.M)
    ok, err = save(SS, t)
    say("ok" if ok else "FAIL", f"{SS}: added invalidate call" if ok else err)
else:
    say("FAIL", f"{SS}: no train_classifier() call found")

print("4) db.py")
replace_function("src/database/db.py", "get_all_enrolled_students_with_parents", PARENTS,
                 skip_if=r"not_\.is_")

print("5) weekly_report_service.py")
WR = "src/services/weekly_report_service.py"
add_import(WR, "from src.services.weekly_data import get_week_stats, get_enrollments_map")
add_import(WR, "from datetime import timedelta, date")
replace_function(WR, "send_weekly_reports_to_all_parents", WEEKLY_MAIN,
                 skip_if=r"get_week_stats\(",
                 need_sig=("send_weekly_parent_email",
                           ["parent_name", "parent_email", "student_name", "roll_no",
                            "section", "subject_reports", "week_start", "week_end"]))

print("6) teacher_screen.py")
replace_function("src/screens/teacher_screen.py", "teacher_tab_enrolled_students", ENROLLED_TAB,
                 skip_if=r"att = defaultdict")

print()
bad = [r for r in RESULTS if r in ("FAIL", "SKIP-MANUAL")]
print(f"Finished. {RESULTS.count('ok')} applied, {RESULTS.count('skip')} already done, {len(bad)} need attention.")
print("Backups are saved as <file>.speedup.bak. Restart Streamlit to see the changes.")
