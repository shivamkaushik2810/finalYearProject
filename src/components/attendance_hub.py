"""One attendance flow: one session per class, many methods, one confirmation."""
from datetime import datetime

import numpy as np
import streamlit as st

from src.database.config import supabase
from src.components import qr_session as qs
from src.components.attendance_scans import record_many, session_id_of
from src.components.nfc_attendance import nfc_panel


def _enrolled(subject_id):
    res = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no, voice_embedding)')\
        .eq('subject_id', subject_id).execute()
    return [e['students'] for e in (res.data or []) if e.get('students')]


# ───────────────────────── photo ─────────────────────────

def _run_face_analysis(session, subject_id, imgs):
    from src.pipelines.face_pipeline import predict_attendance_with_encodings
    from src.pipelines.image_quality import count_faces_in_image
    from src.pipelines.liveness_detection import check_liveness

    found, skipped = set(), 0
    with st.spinner("Scanning classroom photos..."):
        for img in imgs:
            arr = np.array(img.convert("RGB"))
            try:   # anti-spoofing only makes sense for a single-face capture
                if count_faces_in_image(arr) == 1 and not check_liveness(arr)[0]:
                    skipped += 1
                    continue
            except Exception:
                pass
            detected, _, _, _ = predict_attendance_with_encodings(arr)
            found |= set((detected or {}).keys())

    enrolled_ids = {s['student_id'] for s in _enrolled(subject_id)}
    mine = found & enrolled_ids
    added = record_many(session_id_of(session), subject_id, list(mine), 'photo')
    parts = [f"Photos: {len(mine)} enrolled student(s) recognised ({added} newly added)."]
    if found - enrolled_ids:
        parts.append(f"{len(found - enrolled_ids)} recognised face(s) are not enrolled in this subject and were ignored.")
    if skipped:
        parts.append(f"{skipped} photo(s) skipped (possible spoofing).")
    st.session_state['hub_msg'] = ("success" if mine else "warning", " ".join(parts))
    st.rerun()


def _photo_tab(session, subject_id):
    from src.components.dialog_add_photo import add_photos_dialog
    sid = session_id_of(session)
    imgs = st.session_state.attendance_images
    st.caption("Add classroom photos, then run face analysis. Recognised students are added to this session.")
    if st.button("Add photos", type="primary", icon=":material/photo_prints:", key=f"hub_addphoto_{sid}"):
        add_photos_dialog()
    if imgs:
        cols = st.columns(4)
        for i, img in enumerate(imgs):
            with cols[i % 4]:
                st.image(img, width="stretch", caption=f"Photo {i + 1}")
    c1, c2 = st.columns(2)
    if c1.button("Clear photos", type="tertiary", icon=":material/delete:", disabled=not imgs,
                 key=f"hub_clearphoto_{sid}", width="stretch"):
        st.session_state.attendance_images = []
        st.rerun()
    if c2.button("Run face analysis", type="secondary", icon=":material/analytics:", disabled=not imgs,
                 key=f"hub_analyze_{sid}", width="stretch"):
        _run_face_analysis(session, subject_id, imgs)


# ───────────────────────── voice ─────────────────────────

def _voice_tab(session, subject_id):
    from src.pipelines.voice_pipeline import process_bulk_audio
    sid = session_id_of(session)
    st.caption("Record students saying 'I am present'. Students with a voice profile are recognised.")
    audio = st.audio_input("Record classroom audio", key=f"hub_audio_{sid}")
    if st.button("Identify students from audio", type="primary", icon=":material/mic:", key=f"hub_voice_{sid}"):
        if audio is None:
            st.warning("Please record the classroom audio first.")
            return
        candidates = {s['student_id']: s['voice_embedding'] for s in _enrolled(subject_id)
                      if s.get('voice_embedding')}
        if not candidates:
            st.error("No enrolled student has a voice profile registered.")
            return
        with st.spinner("Processing audio..."):
            scores = process_bulk_audio(audio.getvalue(), candidates)
        added = record_many(sid, subject_id, list((scores or {}).keys()), 'voice')
        st.session_state['hub_msg'] = (
            "success" if scores else "warning",
            f"Voice: {len(scores or {})} student(s) recognised ({added} newly added).")
        st.rerun()


# ───────────────────────── stages ─────────────────────────

def _start_card(subject, teacher_id):
    subject_id = subject['subject_id']
    st.markdown("### Start an attendance session")
    st.caption("One session covers every method: QR code, NFC / ID card, class photos and voice. "
               "At the end you review a single list and confirm once. A student can only be saved once per session.")
    allow = True
    try:
        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        last = supabase.table('attendance_logs').select('timestamp')\
            .eq('subject_id', subject_id).gte('timestamp', today)\
            .order('timestamp', desc=True).limit(1).execute().data
        if last:
            st.warning(f"Attendance for this subject was already saved today (around {str(last[0]['timestamp'])[11:16]}).")
            allow = st.checkbox("This is a second class today - start another session",
                                key=f"hub_second_{subject_id}")
    except Exception:
        pass
    st.caption(f"The QR code is accepted for {qs.SESSION_MINUTES} minutes and changes every {qs.ROTATE_SECONDS} seconds. "
               "Photos, voice and NFC can still be added during the review.")
    if st.button("Start attendance session", type="primary", icon=":material/play_circle:",
                 disabled=not allow, key=f"hub_start_{subject_id}"):
        try:
            qs._start_session(subject_id, teacher_id, qs.SESSION_MINUTES)
            st.rerun()
        except Exception as e:
            if 'duplicate' in str(e).lower() or '23505' in str(e):
                st.rerun()
            st.error(f"Could not start session: {e}")


def _live_stage(session, subject_id):
    qs._live_panel(session, subject_id)
    t_qr, t_nfc, t_photo, t_voice = st.tabs(["📱 QR code", "📶 NFC / ID card", "📷 Class photos", "🎤 Voice"])
    with t_qr:
        qs._qr_display(session)
    with t_nfc:
        nfc_panel(session, subject_id, boxed=False)
    with t_photo:
        _photo_tab(session, subject_id)
    with t_voice:
        _voice_tab(session, subject_id)
    if st.button("Stop now & review attendance", type="secondary", icon=":material/stop_circle:",
                 key=f"hub_stop_{session_id_of(session)}"):
        qs._stop_now(session)
        st.rerun()


def _add_more(session, subject_id):
    with st.expander("➕ Add more students (photo / voice / NFC)"):
        t_photo, t_voice, t_nfc = st.tabs(["📷 Class photos", "🎤 Voice", "📶 NFC / ID card"])
        with t_photo:
            _photo_tab(session, subject_id)
        with t_voice:
            _voice_tab(session, subject_id)
        with t_nfc:
            nfc_panel(session, subject_id, boxed=False)


def attendance_hub(subject, teacher_id):
    st.session_state.setdefault('attendance_images', [])
    subject_id = subject['subject_id']

    msg = st.session_state.pop('hub_msg', None)
    if msg:
        (st.success if msg[0] == "success" else st.warning)(msg[1])

    try:
        session = qs._get_active(subject_id)
    except Exception as e:
        st.error("Attendance sessions are not set up yet (database table missing).")
        print(f"hub error: {e}")
        return

    if not session:
        _start_card(subject, teacher_id)
    elif not qs._is_expired(session):
        _live_stage(session, subject_id)
    else:
        qs._review_panel(session, subject_id, teacher_id,
                         between=lambda: _add_more(session, subject_id))
