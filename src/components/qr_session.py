import io
import secrets
import time
from datetime import datetime, timezone, timedelta

import hashlib
import re
from urllib.parse import urlparse, parse_qs

import numpy as np
from PIL import Image
import segno
import streamlit as st

from src.database.config import supabase

APP_URL  = "https://snapclass-main.streamlit.app"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I
CODE_LEN = 6


# ───────────────────────── helpers ─────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _sid(session):
    return session.get('id') if session.get('id') is not None else session.get('session_id')


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


def _session_logs(session):
    res = supabase.table('attendance_logs')\
        .select('student_id, is_present, timestamp')\
        .eq('session_id', _sid(session)).execute()
    return res.data or []


def _end_session(session, subject_id, teacher_id):
    """Marks non-scanners absent, closes the session, returns ALL logs (for emails)."""
    if session.get('teacher_id') not in (None, teacher_id):
        raise PermissionError("This session belongs to another teacher.")

    ts = session.get('session_ts') or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    sid = _sid(session)

    enrolled = supabase.table('subject_students').select('student_id')\
        .eq('subject_id', subject_id).execute().data or []
    done = {l['student_id']: l for l in _session_logs(session)}

    absent_rows = [{
        'student_id': e['student_id'], 'subject_id': subject_id,
        'timestamp': ts, 'is_present': False, 'session_id': sid
    } for e in enrolled if e['student_id'] not in done]

    if absent_rows:
        supabase.table('attendance_logs').insert(absent_rows).execute()

    supabase.table('attendance_sessions').update({'is_active': False}).eq('id', sid).execute() \
        if session.get('id') is not None else \
        supabase.table('attendance_sessions').update({'is_active': False}).eq('session_id', sid).execute()

    all_logs = [{
        'student_id': e['student_id'], 'subject_id': subject_id, 'timestamp': ts,
        'is_present': bool(done.get(e['student_id'], {}).get('is_present'))
    } for e in enrolled]
    return all_logs


def mark_attendance(student_id, code):
    """Student marks themselves present. Returns (ok, message)."""
    code = (code or '').strip().upper()
    if len(code) != CODE_LEN:
        return False, "Please enter the 6-character class code."

    res = supabase.table('attendance_sessions').select('*')\
        .eq('session_code', code).eq('is_active', True).limit(1).execute()
    if not res.data:
        return False, "Invalid code, or the session has ended."
    session = res.data[0]

    if _is_expired(session):
        return False, "⏰ This QR code has expired. Ask your teacher to start a new session."

    subject_id = session['subject_id']
    enrolled = supabase.table('subject_students').select('student_id')\
        .eq('student_id', student_id).eq('subject_id', subject_id).execute()
    if not enrolled.data:
        return False, "You are not enrolled in this subject."

    dup = supabase.table('attendance_logs').select('student_id')\
        .eq('student_id', student_id).eq('session_id', _sid(session)).execute()
    if dup.data:
        return False, "You have already marked attendance for this session."

    try:
        supabase.table('attendance_logs').insert({
            'student_id': student_id,
            'subject_id': subject_id,
            'timestamp':  session.get('session_ts') or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            'is_present': True,
            'session_id': _sid(session),
        }).execute()
    except Exception as e:
        if 'duplicate' in str(e).lower() or '23505' in str(e):
            return False, "You have already marked attendance for this session."
        raise

    sub = supabase.table('subjects').select('name').eq('subject_id', subject_id).execute().data
    return True, f"✅ Attendance marked for {sub[0]['name'] if sub else 'the class'}!"


# ───────────────────────── teacher UI ─────────────────────────

@st.fragment(run_every=3)
def _live_panel(session, subject_id):
    try:
        _live_panel_body(session, subject_id)
    except Exception as e:
        st.caption("Reconnecting to the database...")
        print(f"QR live panel: {e!r}")


def _live_panel_body(session, subject_id):
    expired = _is_expired(session)
    if expired:
        st.warning("⏰ QR expired — late scans are rejected. End the session to mark absentees.")
    else:
        left = int((_parse(session['expires_at']) - _now()).total_seconds())
        st.info(f"⏳ Time left: {left // 60}:{left % 60:02d}")

    present_ids = {l['student_id'] for l in _session_logs(session) if l.get('is_present')}
    enrolled = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no)')\
        .eq('subject_id', subject_id).execute().data or []
    students = [e['students'] for e in enrolled if e.get('students')]

    st.metric("Marked present", f"{len(present_ids)} / {len(students)}")
    names = [f"{s['name']} ({s.get('roll_no') or 'N/A'})" for s in students if s['student_id'] in present_ids]
    if names:
        st.write("✅ " + ", ".join(names))


def teacher_qr_panel(subject, teacher_id):
    st.subheader("📱 QR Attendance")
    st.caption("Students scan the QR, log in with their face, and tap once to mark themselves present.")

    subject_id = subject['subject_id']
    try:
        session = _get_active(subject_id)
    except Exception as e:
        st.error("QR attendance is not set up yet (database table missing). "
                 "Run the Phase 2 SQL in Supabase, then refresh.")
        print(f"QR panel error: {e}")
        return

    if not session:
        minutes = st.select_slider("QR valid for (minutes)", options=[1, 2, 3, 5, 10, 15],
                                   value=5, key=f"qr_min_{subject_id}")
        if st.button("Start QR Session", type="primary", icon=":material/qr_code_2:",
                     key=f"qr_start_{subject_id}"):
            try:
                _start_session(subject_id, teacher_id, minutes)
                st.rerun()
            except Exception as e:
                st.error(f"Could not start session: {e}")
        return

    code = session['session_code']
    url = f"{APP_URL}/?qr-code={code}"

    c1, c2 = st.columns([1, 1])
    with c1:
        st.image(_qr_png(url), width=260, caption="Scan to mark attendance")
    with c2:
        st.markdown("**Class code**")
        st.markdown(f"<div style='font-size:44px;font-weight:bold;letter-spacing:8px;"
                    f"color:#5865F2;'>{code}</div>", unsafe_allow_html=True)
        st.code(url, language="text")

    _live_panel(session, subject_id)

    if st.button("End Session & Mark Absentees", type="secondary", icon=":material/stop_circle:",
                 key=f"qr_end_{subject_id}"):
        try:
            with st.spinner("Closing session..."):
                logs = _end_session(session, subject_id, teacher_id)
            from src.components.dialog_attendance_results import _send_emails
            _send_emails(logs)
            st.toast("✅ Session closed and attendance saved!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Could not close session: {e}")


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
