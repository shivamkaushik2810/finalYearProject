import io
import secrets
import time
from collections import Counter
from datetime import datetime, timezone, timedelta

import hashlib
import hmac
import re
from urllib.parse import urlparse, parse_qs

import numpy as np
import pandas as pd
from PIL import Image
import segno
import streamlit as st

from src.database.config import supabase
from src.components.nfc_attendance import nfc_panel
from src.components.attendance_scans import (
    METHODS, METHOD_LABEL, get_scans, record_scan, session_id_of
)

APP_URL  = "https://snapclass-main.streamlit.app"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I
CODE_LEN = 6

SESSION_MINUTES = 5   # fixed session length
ROTATE_SECONDS = 10   # the QR / code changes every 10 seconds
GRACE_SLOTS    = 1    # also accept the previous code (so a code lives 10-20 s)


def _slot(now=None):
    return int((now or datetime.now(timezone.utc)).timestamp() // ROTATE_SECONDS)


def _token(session, slot):
    sid = session.get('id') if session.get('id') is not None else session.get('session_id')
    key = f"{sid}:{session['session_code']}".encode()
    digest = hmac.new(key, str(slot).encode(), hashlib.sha256).digest()
    return ''.join(ALPHABET[b % len(ALPHABET)] for b in digest[:CODE_LEN])


def _valid_tokens(session):
    cur = _slot()
    return {_token(session, cur - i) for i in range(GRACE_SLOTS + 1)}


# ───────────────────────── helpers ─────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time(ts):
    try:
        return _parse(ts).astimezone().strftime("%I:%M:%S %p")
    except Exception:
        return str(ts or "")


def _sid(session):
    return session_id_of(session)


def _id_col(session):
    return 'id' if session.get('id') is not None else 'session_id'


def _is_expired(session):
    try:
        return _now() >= _parse(session['expires_at'])
    except Exception:
        return True


def _qr_png(url):
    qr = segno.make(url)
    out = io.BytesIO()
    qr.save(out, kind='png', scale=8, border=1)
    return out.getvalue()


def _new_code():
    for _ in range(20):
        code = ''.join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
        clash = supabase.table('attendance_sessions').select('session_code')\
            .eq('session_code', code).eq('is_active', True).execute()
        if not clash.data:
            return code
    raise RuntimeError("Could not generate a unique code, try again.")


# ───────────────────────── session logic ─────────────────────────

def _get_active(subject_id):
    res = supabase.table('attendance_sessions').select('*')\
        .eq('subject_id', subject_id).eq('is_active', True)\
        .order('expires_at', desc=True).limit(1).execute()
    return res.data[0] if res.data else None


def _start_session(subject_id, teacher_id, minutes):
    now = _now()
    row = {
        'subject_id':   subject_id,
        'teacher_id':   teacher_id,
        'session_code': _new_code(),
        'is_active':    True,
        'expires_at':   (now + timedelta(minutes=minutes)).isoformat(),
        'session_ts':   datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    res = supabase.table('attendance_sessions').insert(row).execute()
    return res.data[0]


def _stop_now(session):
    """Ends the scanning window immediately (late scans are rejected)."""
    supabase.table('attendance_sessions').update({'expires_at': _now().isoformat()})\
        .eq(_id_col(session), _sid(session)).execute()


def _close(session):
    supabase.table('attendance_sessions').update({'is_active': False})\
        .eq(_id_col(session), _sid(session)).execute()


def _discard_session(session):
    supabase.table('attendance_scans').delete().eq('session_id', _sid(session)).execute()
    _close(session)
    st.session_state['attendance_images'] = []


def _insert_logs(rows):
    """Inserts the confirmed rows. Falls back gracefully if the 'method' column is missing."""
    with_method = True
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        if not with_method:
            chunk = [{k: v for k, v in r.items() if k != 'method'} for r in chunk]
        try:
            supabase.table('attendance_logs').insert(chunk).execute()
        except Exception as e:
            if with_method and 'method' in str(e).lower():
                with_method = False
                chunk = [{k: v for k, v in r.items() if k != 'method'} for r in chunk]
                supabase.table('attendance_logs').insert(chunk).execute()
            else:
                raise


def _confirm_session(session, subject_id, teacher_id, present_ids, methods_by_student):
    """Writes the teacher-confirmed attendance for ALL enrolled students, closes the
    session and returns the logs (used for the emails)."""
    if session.get('teacher_id') not in (None, teacher_id):
        raise PermissionError("This session belongs to another teacher.")

    sid = _sid(session)
    already = supabase.table('attendance_logs').select('id')\
        .eq('session_id', sid).limit(1).execute().data
    if already:
        raise RuntimeError("Attendance for this session was already saved.")

    ts = session.get('session_ts') or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    enrolled = supabase.table('subject_students').select('student_id')\
        .eq('subject_id', subject_id).execute().data or []
    order = [k for k, _ in METHODS]

    rows = []
    for e in enrolled:
        stu = e['student_id']
        present = stu in present_ids
        used = sorted(methods_by_student.get(stu, set()), key=lambda m: order.index(m) if m in order else 99)
        method = ("+".join(used) if used else "manual") if present else None
        rows.append({'student_id': stu, 'subject_id': subject_id, 'timestamp': ts,
                     'is_present': present, 'session_id': sid, 'method': method})

    _insert_logs(rows)
    _close(session)
    st.session_state['attendance_images'] = []
    return [{'student_id': r['student_id'], 'subject_id': subject_id,
             'timestamp': ts, 'is_present': r['is_present']} for r in rows]


def mark_attendance(student_id, code):
    """Student scans in with QR. The scan is held as pending until the teacher confirms.
    Returns (ok, message)."""
    code = (code or '').strip().upper()
    if len(code) != CODE_LEN:
        return False, "Please enter the 6-character class code."

    res = supabase.table('attendance_sessions').select('*')\
        .eq('is_active', True).execute()
    session = next((x for x in (res.data or []) if code in _valid_tokens(x)), None)
    if not session:
        return False, "Invalid or expired code. Scan the live QR on the teacher's screen again."

    if _is_expired(session):
        return False, "⏰ This QR code has expired. Ask your teacher to start a new session."

    subject_id = session['subject_id']
    enrolled = supabase.table('subject_students').select('student_id')\
        .eq('student_id', student_id).eq('subject_id', subject_id).execute()
    if not enrolled.data:
        return False, "You are not enrolled in this subject."

    ok, _ = record_scan(_sid(session), student_id, subject_id, 'qr')
    if not ok:
        return False, "You have already marked attendance for this session."

    sub = supabase.table('subjects').select('name').eq('subject_id', subject_id).execute().data
    return True, f"✅ Attendance marked for {sub[0]['name'] if sub else 'the class'}!"


# ───────────────────────── teacher UI ─────────────────────────

@st.fragment(run_every=3)
def _live_panel(session, subject_id):
    if _is_expired(session):
        st.rerun()          # time is up -> the page switches to the review list
    try:
        _live_panel_body(session, subject_id)
    except Exception as e:
        st.caption("Reconnecting to the database...")
        print(f"QR live panel: {e!r}")


def _live_panel_body(session, subject_id):
    left = int((_parse(session['expires_at']) - _now()).total_seconds())
    st.info(f"⏳ Time left: {max(left, 0) // 60}:{max(left, 0) % 60:02d}")

    scans = get_scans(_sid(session))
    marked = {r['student_id'] for r in scans}
    counts = Counter(r.get('method') for r in scans)
    enrolled = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no)')\
        .eq('subject_id', subject_id).execute().data or []
    students = [e['students'] for e in enrolled if e.get('students')]

    st.metric("Marked so far (all methods)", f"{len(marked)} / {len(students)}")
    st.caption(" · ".join(f"{label}: {counts.get(key, 0)}" for key, label in METHODS))
    names = [f"{s['name']} ({s.get('roll_no') or 'N/A'})" for s in students if s['student_id'] in marked]
    if names:
        st.write("✅ " + ", ".join(names))


@st.fragment(run_every=2)
def _qr_display(session):
    if _is_expired(session):
        return
    code = _token(session, _slot())
    url = f"{APP_URL}/?qr-code={code}"
    left = ROTATE_SECONDS - int(_now().timestamp() % ROTATE_SECONDS)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.image(_qr_png(url), width=260, caption="Scan to mark attendance")
    with c2:
        st.markdown("**Class code**")
        st.markdown(f"<div style='font-size:44px;font-weight:bold;letter-spacing:8px;"
                    f"color:#5865F2;'>{code}</div>", unsafe_allow_html=True)
        st.caption(f"🔄 Code changes in {left}s")
        st.progress(left / ROTATE_SECONDS)


def _review_panel(session, subject_id, teacher_id, between=None):
    """Full class list with the method(s) each student used. Nothing is saved until the teacher confirms."""
    sid = _sid(session)
    enrolled = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no)')\
        .eq('subject_id', subject_id).execute().data or []
    students = [e['students'] for e in enrolled if e.get('students')]
    scans = get_scans(sid)

    methods_by_student = {}
    for r in scans:
        methods_by_student.setdefault(r['student_id'], set()).add(r.get('method'))

    if not students:
        st.warning("No students are enrolled in this subject.")
        if st.button("Close session", key=f"qr_close_{sid}"):
            _discard_session(session)
            st.rerun()
        return

    students.sort(key=lambda s: ((s.get('roll_no') or ''), s['name']))
    rows = []
    for s in students:
        used = methods_by_student.get(s['student_id'], set())
        row = {"student_id": s['student_id'], "Roll No": s.get('roll_no') or "N/A", "Name": s['name']}
        for key, label in METHODS:
            row[label] = "✅" if key in used else "—"
        row["Present"] = bool(used)
        rows.append(row)
    df = pd.DataFrame(rows)

    st.success(f"⏰ Session finished. {len(methods_by_student)} of {len(students)} students marked themselves "
               "(QR / NFC / Voice / Photo). Review the list, then confirm. Nothing is saved until you confirm.")

    with st.expander(f"📋 Review attendance — {len(methods_by_student)} of {len(students)} marked", expanded=True):
        st.caption("Tick or untick **Present** to correct anyone. Students you tick by hand are saved as 'manual'.")
        edited = st.data_editor(
            df, hide_index=True, key=f"qr_review_{sid}", width="stretch",
            disabled=["Roll No", "Name"] + [label for _, label in METHODS],
            column_config={"student_id": None,
                           "Present": st.column_config.CheckboxColumn("Present")})

        present_ids = {s_ for s_, p in zip(edited["student_id"], edited["Present"]) if bool(p)}
        manual = [s_ for s_ in present_ids if not methods_by_student.get(s_)]

        m1, m2, m3 = st.columns(3)
        m1.metric("Present", len(present_ids))
        m2.metric("Absent", len(students) - len(present_ids))
        m3.metric("Total", len(students))

        counts = Counter(r.get('method') for r in scans)
        st.caption(" · ".join(f"{label}: {counts.get(key, 0)}" for key, label in METHODS)
                   + f" · Manual (teacher): {len(manual)}")

        b1, b2 = st.columns(2)
        if b1.button("Confirm & Save to database", type="primary", icon=":material/check_circle:",
                     key=f"qr_confirm_{sid}", width="stretch"):
            try:
                with st.spinner("Saving attendance..."):
                    logs = _confirm_session(session, subject_id, teacher_id, present_ids, methods_by_student)
                from src.components.dialog_attendance_results import _send_emails
                _send_emails(logs)
                st.toast("✅ Attendance saved!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Could not save attendance: {e}")
        if b2.button("Discard session (save nothing)", icon=":material/delete:",
                     key=f"qr_discard_{sid}", width="stretch"):
            _discard_session(session)
            st.rerun()

    if between:
        between()

    with st.expander("🕒 Activity log — who marked attendance and how"):
        if not scans:
            st.caption("No student marked attendance yet.")
        else:
            info = {s['student_id']: s for s in students}
            log_rows = [{
                "Time": _fmt_time(r.get('scanned_at')),
                "Roll No": (info.get(r['student_id']) or {}).get('roll_no') or "N/A",
                "Name": (info.get(r['student_id']) or {}).get('name', "Unknown"),
                "Method": METHOD_LABEL.get(r.get('method'), r.get('method')),
            } for r in sorted(scans, key=lambda r: str(r.get('scanned_at') or ''))]
            st.dataframe(pd.DataFrame(log_rows), hide_index=True, width="stretch")


def teacher_qr_panel(subject, teacher_id):
    st.subheader("📱 QR Attendance")
    st.caption("Students can mark attendance by QR, NFC, voice or photo. When the session ends you review the "
               "full list with the method each student used and confirm before anything is saved.")

    subject_id = subject['subject_id']
    try:
        session = _get_active(subject_id)
    except Exception as e:
        st.error("QR attendance is not set up yet (database table missing). "
                 "Run the Phase 2 SQL in Supabase, then refresh.")
        print(f"QR panel error: {e}")
        return

    if not session:
        st.caption(f"Session stays open for {SESSION_MINUTES} minutes. The QR code changes every {ROTATE_SECONDS} seconds.")
        if st.button("Start QR Session", type="primary", icon=":material/qr_code_2:",
                     key=f"qr_start_{subject_id}"):
            try:
                _start_session(subject_id, teacher_id, SESSION_MINUTES)
                st.rerun()
            except Exception as e:
                st.error(f"Could not start session: {e}")
        return

    if not _is_expired(session):
        _qr_display(session)
        _live_panel(session, subject_id)
        nfc_panel(session, subject_id)
        if st.button("Stop now & review attendance", type="secondary", icon=":material/stop_circle:",
                     key=f"qr_stop_{subject_id}"):
            _stop_now(session)
            st.rerun()
        return

    _review_panel(session, subject_id, teacher_id)


# ───────────────────────── student UI ─────────────────────────

def _decode_qr(image_bytes):
    """Decode a QR code from a photo. Returns the text or None."""
    import cv2
    img = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    detector = cv2.QRCodeDetector()
    candidates = [img, cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)]
    h, w = img.shape[:2]
    if max(h, w) < 1400:
        candidates.append(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    for c in candidates:
        data, _, _ = detector.detectAndDecode(c)
        if data:
            return data
    return None


def _extract_code(data):
    """Accepts the full join URL (?qr-code=XXXXXX) or a bare 6-character code."""
    data = (data or "").strip()
    try:
        q = parse_qs(urlparse(data).query)
        if q.get("qr-code"):
            return q["qr-code"][0].strip().upper()
    except Exception:
        pass
    if re.fullmatch(r"[A-Za-z0-9]{6}", data):
        return data.upper()
    return None


def student_qr_panel(student, key_prefix="qr"):
    st.subheader("📱 Mark Attendance with QR Code")
    result_key = f"{key_prefix}_result"
    last_key = f"{key_prefix}_last_photo"
    prefill = (st.query_params.get('qr-code') or "").strip().upper()

    tab_cam, tab_code = st.tabs(["📷 Scan with camera", "⌨️ Enter code"])

    with tab_cam:
        st.caption("Hold the QR code on the teacher's screen steadily in front of the camera, then take the photo.")
        photo = st.camera_input("Scan the class QR code", key=f"{key_prefix}_cam")
        if photo is not None:
            raw = photo.getvalue()
            digest = hashlib.md5(raw).hexdigest()
            # process each photo only once (Streamlit reruns the script on every interaction)
            if st.session_state.get(last_key) != digest:
                st.session_state[last_key] = digest
                code = _extract_code(_decode_qr(raw))
                if not code:
                    st.session_state[result_key] = (False, "No QR code found in the photo. Move closer, hold steady and retake.")
                else:
                    try:
                        st.session_state[result_key] = mark_attendance(student['student_id'], code)
                    except Exception as e:
                        st.session_state[result_key] = (False, f"Could not mark attendance: {e}")
                    if st.session_state[result_key][0]:
                        st.balloons()

    with tab_code:
        code = st.text_input("Class code", value=prefill, max_chars=8,
                             placeholder="e.g. K7M2QX", key=f"{key_prefix}_code").strip().upper()
        if st.button("Mark Me Present", type="primary", icon=":material/how_to_reg:",
                     key=f"{key_prefix}_btn"):
            try:
                ok, msg = mark_attendance(student['student_id'], code)
            except Exception as e:
                ok, msg = False, f"Could not mark attendance: {e}"
            st.session_state[result_key] = (ok, msg)
            if ok:
                st.balloons()
                if 'qr-code' in st.query_params:
                    del st.query_params['qr-code']

    res = st.session_state.get(result_key)
    if res:
        (st.success if res[0] else st.error)(res[1])
