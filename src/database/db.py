from datetime import date, timedelta
import bcrypt
from src.services.email_rules import emails_conflict
import streamlit as st
from src.database.config import supabase

STUDENT_LIGHT_COLS = "student_id, name, email, roll_no, section, year, course, parent_email, parent_name"
PAGE = 1000  # Supabase returns max 1000 rows per request


# ───────────────────────── helpers ─────────────────────────
def _fetch_all(build, order=()):
    """Fetch every row (beyond the 1000-row cap). `build` returns a fresh query."""
    rows, start = [], 0
    while True:
        q = build()
        for col in order:
            q = q.order(col)
        chunk = q.range(start, start + PAGE - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < PAGE:
            return rows
        start += PAGE


def _to_date(d):
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


# ───────────────────────── auth ─────────────────────────
def hash_pass(pwd):
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()


def check_pass(pwd, hashed):
    return bcrypt.checkpw(pwd.encode(), hashed.encode())


def check_teacher_exists(username):
    r = supabase.table("teachers").select("username").eq("username", username).limit(1).execute()
    return len(r.data) > 0


def create_teacher(username, password, name, email=None):
    data = {"username": username, "password": hash_pass(password),
            "name": name, "email": email}
    return supabase.table("teachers").insert(data).execute().data


def teacher_login(username, password):
    r = supabase.table("teachers").select("*").eq("username", username).limit(1).execute()
    if r.data:
        teacher = r.data[0]
        if check_pass(password, teacher['password']):
            return teacher
    return None


# ───────────────────────── students ─────────────────────────
def get_all_students():
    """HEAVY (includes embeddings). Only use for model training."""
    return _fetch_all(lambda: supabase.table('students').select("*"), order=('student_id',))


def get_student_by_id(student_id):
    r = supabase.table('students').select("*").eq('student_id', student_id).limit(1).execute()
    return r.data[0] if r.data else None


def get_student_names():
    """{student_id: {student_id, name}} without embeddings (for logging/printing)."""
    rows = _fetch_all(lambda: supabase.table('students').select("student_id, name"),
                      order=('student_id',))
    return {s['student_id']: s for s in rows}


def count_students():
    r = supabase.table('students').select('student_id', count='exact').limit(1).execute()
    return r.count or 0


def create_student(new_name, face_embedding=None, voice_embedding=None,
                   email=None, roll_no=None, section=None,
                   parent_email=None, parent_name=None, year=None, course=None):
    if email and parent_email and emails_conflict(email, parent_email):
        raise ValueError("Student email and parent email must be different.")

    data = {
        'name': new_name, 'face_embedding': face_embedding,
        'voice_embedding': voice_embedding, 'email': email,
        'roll_no': roll_no, 'section': section,
        'parent_email': parent_email, 'parent_name': parent_name,
        'year': year, 'course': course
    }
    return supabase.table('students').insert(data).execute().data


# ───────────────────────── marks ─────────────────────────
def add_marks(student_id, subject_id, teacher_id, marks_obtained,
              max_marks=100, exam_type='Internal', remarks=None, exam_date=None):
    _validate_marks(marks_obtained, max_marks)
    if not _teacher_owns_subject(teacher_id, subject_id):
        raise PermissionError("You can only add marks for your own subjects.")
    data = {
        'student_id':     student_id,
        'subject_id':     subject_id,
        'teacher_id':     teacher_id,
        'marks_obtained': marks_obtained,
        'max_marks':      max_marks,
        'exam_type':      exam_type,
        'remarks':        remarks,
        'exam_date':      str(exam_date) if exam_date else None,
        'entry_status':   'entered'
    }
    response = supabase.table('marks').insert(data).execute()
    return response.data


def update_marks(mark_id, marks_obtained, max_marks=100,
                 exam_type='Internal', remarks=None, teacher_id=None, exam_date=None):
    _validate_marks(marks_obtained, max_marks)
    if teacher_id is not None and not _teacher_owns_mark(teacher_id, mark_id):
        raise PermissionError("You can only edit marks for your own subjects.")
    data = {
        'marks_obtained': marks_obtained,
        'max_marks':      max_marks,
        'exam_type':      exam_type,
        'remarks':        remarks,
        'exam_date':      str(exam_date) if exam_date else None,
        'entry_status':   'entered'
    }
    response = supabase.table('marks').update(data)\
        .eq('id', mark_id).execute()
    return response.data


def get_marks_by_subject(subject_id, verified_only=False):
    def _build():
        q = supabase.table('marks')\
            .select('*, students(name, roll_no, section, year)')\
            .eq('subject_id', subject_id)
        if verified_only:
            q = q.neq('entry_status', 'unverified')
        return q
    return _fetch_all(_build, order=('id',))


def get_marks_by_student(student_id):
    return _fetch_all(
        lambda: supabase.table('marks')
        .select('*, subjects(name, subject_code)')
        .eq('student_id', student_id),
        order=('id',))


def delete_marks(mark_id, teacher_id=None):
    if teacher_id is not None and not _teacher_owns_mark(teacher_id, mark_id):
        raise PermissionError("You can only delete marks for your own subjects.")
    response = supabase.table('marks').delete()\
        .eq('id', mark_id).execute()
    return response.data


# ───────────────────────── subjects ─────────────────────────
def create_subject(subject_code, name, section, teacher_id, course=None, year=None):
    data = {
        "subject_code": subject_code,
        "name":         name,
        "section":      section,
        "teacher_id":   teacher_id
    }
    if course:
        data["course"] = course
    if year:
        data["year"] = str(year)
    response = supabase.table("subjects").insert(data).execute()
    return response.data


@st.cache_data(ttl=30, show_spinner=False)
def get_teacher_subjects(teacher_id):
    subjects = supabase.table('subjects').select("*").eq("teacher_id", teacher_id).execute().data or []
    if not subjects:
        return []
    ids = [s['subject_id'] for s in subjects]
    stats = supabase.table('subject_stats')\
        .select('subject_id, total_students, total_classes')\
        .in_('subject_id', ids).execute().data or []
    smap = {r['subject_id']: r for r in stats}
    for s in subjects:
        r = smap.get(s['subject_id'], {})
        s['total_students'] = r.get('total_students', 0)
        s['total_classes'] = r.get('total_classes', 0)
    return subjects


def enroll_student_to_subject(student_id, subject_id):
    data = {'student_id': student_id, "subject_id": subject_id}
    r = supabase.table('subject_students').insert(data).execute().data
    get_student_subjects.clear()
    get_teacher_subjects.clear()
    return r


def unenroll_student_to_subject(student_id, subject_id):
    r = supabase.table('subject_students').delete()\
        .eq('student_id', student_id).eq('subject_id', subject_id).execute().data
    get_student_subjects.clear()
    get_teacher_subjects.clear()
    return r


@st.cache_data(ttl=30, show_spinner=False)
def get_student_subjects(student_id):
    return supabase.table('subject_students')\
        .select('subject_id, subjects(subject_id, name, subject_code, section)')\
        .eq('student_id', student_id).execute().data


@st.cache_data(ttl=30, show_spinner=False)
def get_student_attendance(student_id):
    return _fetch_all(
        lambda: supabase.table('attendance_logs')
        .select('subject_id, is_present, timestamp')
        .eq('student_id', student_id),
        order=('timestamp', 'subject_id'))


# ───────────────────────── attendance ─────────────────────────
def create_attendance(logs):
    r = supabase.table('attendance_logs').insert(logs).execute().data
    get_teacher_subjects.clear()
    get_student_attendance.clear()
    return r


def get_attendance_for_teacher(teacher_id):
    return _fetch_all(
        lambda: supabase.table('attendance_logs')
        .select("timestamp, is_present, subjects!inner(name, subject_code, teacher_id)")
        .eq('subjects.teacher_id', teacher_id),
        order=('timestamp', 'subject_id', 'student_id'))


def get_subject_logs(subject_id):
    """Only the columns the AI Insights tab needs."""
    return _fetch_all(
        lambda: supabase.table('attendance_logs')
        .select('student_id, is_present, timestamp')
        .eq('subject_id', subject_id),
        order=('timestamp', 'student_id'))


def get_subject_students_detail(subject_id):
    rows = _fetch_all(
        lambda: supabase.table('subject_students')
        .select('student_id, students(student_id, name, email, roll_no, section, parent_email)')
        .eq('subject_id', subject_id),
        order=('student_id',))
    return [r['students'] for r in rows if r.get('students')]


def get_subject_student_stats(subject_id):
    """{student_id: (total, present)} from the student_subject_stats view."""
    rows = _fetch_all(
        lambda: supabase.table('student_subject_stats')
        .select('student_id, total, present').eq('subject_id', subject_id),
        order=('student_id',))
    return {r['student_id']: (r['total'], r['present']) for r in rows}


# ───────────────────────── weekly reports ─────────────────────────
def get_weekly_attendance(student_id, subject_id, start_iso, end_exclusive_iso):
    """Logs with start_iso <= timestamp < end_exclusive_iso (full days included)."""
    response = supabase.table('attendance_logs')\
        .select('*')\
        .eq('student_id', student_id)\
        .eq('subject_id', subject_id)\
        .gte('timestamp', start_iso)\
        .lt('timestamp', end_exclusive_iso)\
        .execute()
    return response.data


def get_weekly_attendance_bulk(week_start, week_end):
    """ONE paginated query for the whole week -> {(student_id, subject_id): (total, attended)}"""
    start = str(_to_date(week_start))
    end = str(_to_date(week_end) + timedelta(days=1))
    rows = _fetch_all(
        lambda: supabase.table('attendance_logs')
        .select('student_id, subject_id, is_present, status')
        .gte('timestamp', start).lt('timestamp', end),
        order=('timestamp', 'subject_id', 'student_id'))
    agg = {}
    for r in eligible(rows):
        key = (r['student_id'], r['subject_id'])
        t, a = agg.get(key, (0, 0))
        agg[key] = (t + 1, a + (1 if r.get('is_present') else 0))
    return agg


def get_enrolled_subjects_map():
    """ONE query -> {student_id: [{subject_id, name, subject_code}, ...]}"""
    rows = _fetch_all(
        lambda: supabase.table('subject_students')
        .select('student_id, subjects(subject_id, name, subject_code)'),
        order=('student_id', 'subject_id'))
    out = {}
    for r in rows:
        if r.get('subjects'):
            out.setdefault(r['student_id'], []).append(r['subjects'])
    return out


def get_reported_student_ids(week_start):
    rows = _fetch_all(
        lambda: supabase.table('weekly_reports').select('student_id')
        .eq('week_start', str(_to_date(week_start))),
        order=('student_id', 'subject_id'))
    return {r['student_id'] for r in rows}


def save_weekly_report(student_id, subject_id, week_start, week_end,
                       total, attended, absent, pct, email_sent=True):
    """Save weekly report record (call AFTER the email was actually sent)."""
    data = {
        'student_id':      student_id,
        'subject_id':      subject_id,
        'week_start':      str(week_start),
        'week_end':        str(week_end),
        'total_classes':   total,
        'attended':        attended,
        'absent':          absent,
        'attendance_pct':  pct,
        'email_sent':      email_sent
    }
    response = supabase.table('weekly_reports').insert(data).execute()
    return response.data


def save_weekly_reports_bulk(rows, chunk=500):
    for i in range(0, len(rows), chunk):
        supabase.table('weekly_reports')\
            .upsert(rows[i:i + chunk], on_conflict='student_id,subject_id,week_start').execute()


def get_all_enrolled_students_with_parents():
    return _fetch_all(
        lambda: supabase.table('students').select(STUDENT_LIGHT_COLS)
        .not_.is_('parent_email', 'null'),
        order=('student_id',))


def get_subjects_for_student(student_id):
    return supabase.table('subject_students')\
        .select('subjects(subject_id, name, subject_code)')\
        .eq('student_id', student_id).execute().data


# ───── restored from previous db.py ─────
def check_section_match(student_id, subject_id):
    """Returns (ok, message). A student may only enroll in subjects of their own section."""
    stu = supabase.table('students').select('section').eq('student_id', student_id).execute().data
    sub = supabase.table('subjects').select('section, name').eq('subject_id', subject_id).execute().data
    if not stu or not sub:
        return False, "Student or subject not found."
    s_sec, sub_sec = _norm_section(stu[0].get('section')), _norm_section(sub[0].get('section'))
    if not s_sec:
        return False, "Your profile has no section. Please contact your administrator."
    if s_sec != sub_sec:
        return False, (f"This subject is for Section {sub[0].get('section') or '?'}, "
                       f"but you are in Section {stu[0].get('section')}. You can only enroll in your own section's subjects.")
    return True, ""


def teacher_login_checked(username, password):
    """Returns (teacher or None, message). 5 wrong passwords lock the account for 5 minutes."""
    from datetime import datetime, timezone, timedelta
    res = supabase.table("teachers").select("*").eq("username", (username or "").strip()).execute()
    if not res.data:
        check_pass(password or "", _DUMMY_HASH)   # similar timing for unknown usernames
        return None, ""
    teacher = res.data[0]

    locked = teacher.get("locked_until")
    if locked:
        try:
            until = datetime.fromisoformat(str(locked).replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < until:
                return None, "Too many failed attempts. Try again in a few minutes."
        except Exception:
            pass

    try:
        if check_pass(password or "", teacher["password"]):
            if teacher.get("failed_attempts") or locked:
                supabase.table("teachers").update({"failed_attempts": 0, "locked_until": None})\
                    .eq("teacher_id", teacher["teacher_id"]).execute()
            return teacher, ""

        fails = (teacher.get("failed_attempts") or 0) + 1
        upd = {"failed_attempts": fails}
        if fails >= 5:
            upd = {"failed_attempts": 0,
                   "locked_until": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
        supabase.table("teachers").update(upd).eq("teacher_id", teacher["teacher_id"]).execute()
    except Exception as e:
        print(f"Teacher lockout bookkeeping failed: {e}")
    return None, ""


def get_subject_attendance_stats(subject_id):
    """{student_id: {'total': n, 'present': n}} for one subject.
    Paginated (no 1000-row cap); cancelled classes and excused absences are left out."""
    rows = _fetch_all(
        lambda: supabase.table('attendance_logs')
        .select('student_id, is_present, status')
        .eq('subject_id', subject_id),
        order=('timestamp', 'student_id'))
    stats = {}
    for row in eligible(rows):
        s = stats.setdefault(row['student_id'], {'total': 0, 'present': 0})
        s['total'] += 1
        if row.get('is_present'):
            s['present'] += 1
    return stats


def admin_login(username, password):
    """Returns (admin_dict or None, message). 5 wrong passwords lock the account for 5 minutes."""
    from datetime import datetime, timezone, timedelta
    generic = "Invalid username or password."
    res = supabase.table('admins').select('*').eq('username', (username or '').strip()).execute()
    if not res.data:
        return None, generic
    admin = res.data[0]

    locked = admin.get('locked_until')
    if locked:
        try:
            until = datetime.fromisoformat(str(locked).replace('Z', '+00:00'))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < until:
                return None, "Too many failed attempts. Try again in a few minutes."
        except Exception:
            pass

    if check_pass(password or '', admin['password']):
        supabase.table('admins').update({'failed_attempts': 0, 'locked_until': None})\
            .eq('id', admin['id']).execute()
        return admin, ""

    fails = (admin.get('failed_attempts') or 0) + 1
    upd = {'failed_attempts': fails}
    if fails >= 5:
        upd = {'failed_attempts': 0,
               'locked_until': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
    supabase.table('admins').update(upd).eq('id', admin['id']).execute()
    return None, generic


def get_teachers_by_status(status):
    res = supabase.table('teachers')\
        .select('teacher_id, username, name, email, status')\
        .eq('status', status).order('name').execute()
    return res.data or []


def set_teacher_status(teacher_id, status):
    if status not in ('approved', 'rejected', 'pending'):
        raise ValueError("Invalid status")
    return supabase.table('teachers').update({'status': status})\
        .eq('teacher_id', teacher_id).execute().data


def get_children_for_parent(parent_email):
    """
    Students a parent may view: those whose (OTP-verified) parent_email matches,
    plus verified rows in parent_student_links. Matching is exact, case-insensitive.
    """
    email = (parent_email or '').strip().lower()
    if not email:
        return []

    ids = set()
    cols = 'student_id, name, roll_no, section, course, year, parent_email, parent_name'

    # ilike can treat '_' / '%' as wildcards, so we re-check equality in Python
    res = supabase.table('students').select(cols).ilike('parent_email', email).execute()
    children = {}
    for s in (res.data or []):
        if (s.get('parent_email') or '').strip().lower() == email:
            children[s['student_id']] = s

    try:
        links = supabase.table('parent_student_links')\
            .select('student_id, parent_email')\
            .eq('is_verified', True)\
            .ilike('parent_email', email).execute()
        ids = {l['student_id'] for l in (links.data or [])
               if (l.get('parent_email') or '').strip().lower() == email}
    except Exception as e:
        print(f"parent_student_links lookup failed: {e}")

    missing = [i for i in ids if i not in children]
    if missing:
        extra = supabase.table('students').select(cols).in_('student_id', missing).execute()
        for s in (extra.data or []):
            children[s['student_id']] = s

    return sorted(children.values(), key=lambda s: (s.get('name') or '').lower())


def weekly_report_exists(student_id, week_start):
    """True if a report for this student+week was already emailed."""
    response = supabase.table('weekly_reports')\
        .select('student_id')\
        .eq('student_id', student_id)\
        .eq('week_start', str(week_start))\
        .eq('email_sent', True)\
        .limit(1).execute()
    return bool(response.data)


# clear cached subject lists after a subject is created
_create_subject_uncached = create_subject
def create_subject(*args, **kwargs):
    result = _create_subject_uncached(*args, **kwargs)
    get_teacher_subjects.clear()
    return result


# restored from db.py.old
_DUMMY_HASH = hash_pass("not-a-real-password")


# restored from db.py.old
def _norm_section(v):
    return (v or "").strip().upper()


# restored from db.py.old
def _teacher_owns_mark(teacher_id, mark_id):
    r = supabase.table('marks').select('subject_id').eq('id', mark_id).execute()
    return bool(r.data) and _teacher_owns_subject(teacher_id, r.data[0]['subject_id'])


# restored from db.py.old
def _teacher_owns_subject(teacher_id, subject_id):
    r = supabase.table('subjects').select('subject_id')\
        .eq('subject_id', subject_id).eq('teacher_id', teacher_id).execute()
    return bool(r.data)


# restored from db.py.old
def _validate_marks(marks_obtained, max_marks):
    try:
        m, mx = float(marks_obtained), float(max_marks)
    except (TypeError, ValueError):
        raise ValueError("Marks must be numbers.")
    if mx <= 0:
        raise ValueError("Maximum marks must be greater than 0.")
    if m < 0 or m > mx:
        raise ValueError(f"Marks must be between 0 and {mx:g}.")


def eligible(rows):
    """Resolved lazily so importing db.py never creates a circular import."""
    from src.database.attendance_status import eligible as _eligible
    return _eligible(rows)


def get_subject_logs_full(subject_id):
    """All attendance rows of one subject, every column, no 1000-row cap."""
    return _fetch_all(
        lambda: supabase.table('attendance_logs').select('*').eq('subject_id', subject_id),
        order=('timestamp', 'student_id'))


def weekly_report_already_sent(student_id, week_start):
    """True if a successfully sent report exists for this student and week."""
    response = supabase.table('weekly_reports')\
        .select('student_id')\
        .eq('student_id', student_id)\
        .eq('week_start', str(week_start))\
        .eq('email_sent', True)\
        .limit(1)\
        .execute()
    return bool(response.data)


def create_attendance_idempotent(logs):
    """Insert attendance rows, skipping rows that already exist
    (unique on student_id, subject_id, timestamp).
    Returns ONLY the rows that were newly inserted."""
    if not logs:
        return []
    response = supabase.table('attendance_logs').upsert(
        logs,
        on_conflict='student_id,subject_id,timestamp',
        ignore_duplicates=True
    ).execute()
    return response.data or []
