import logging
import time

import streamlit as st

from src.database.config import supabase
from src.database.db import create_attendance_idempotent
from src.services.email_queue import enqueue_attendance_emails

log = logging.getLogger("snapclass.attendance")


def show_attendance_result(df, logs):
    st.write('Please review attendance before confirming.')
    st.dataframe(df, hide_index=True, width='stretch')

    col1, col2 = st.columns(2)

    with col1:
        if st.button('Discard', width='stretch'):
            st.session_state.voice_attendance_results = None
            st.session_state.attendance_images = []
            st.rerun()

    with col2:
        if st.button('Confirm & Save', width='stretch', type='primary'):
            _confirm_and_save(logs)


def _confirm_and_save(logs):
    if not logs:
        st.warning("Nothing to save.")
        return

    token = f"{logs[0]['subject_id']}|{logs[0]['timestamp']}"
    saved_tokens = st.session_state.setdefault("saved_attendance_tokens", set())
    if token in saved_tokens:  # double-click guard (DB unique index is the real guard)
        st.info("This attendance session was already saved.")
        return

    try:
        inserted = create_attendance_idempotent(logs)
    except Exception:
        log.exception("attendance save failed")
        st.error("Could not save attendance. Nothing was recorded — please try again.")
        return

    saved_tokens.add(token)

    if not inserted:
        st.toast("ℹ️ Already saved earlier — no duplicates created, no emails re-sent.")
    else:
        st.toast("✅ Attendance saved!")
        new_ids = {r['student_id'] for r in inserted}
        _learn_from_confirmed([l for l in logs if l['student_id'] in new_ids])
        _queue_emails(logs, inserted)

    st.session_state.attendance_images = []
    st.session_state.voice_attendance_results = None
    time.sleep(1)
    st.rerun()


def _queue_emails(all_logs, inserted):
    """Queue emails only for rows that were actually inserted just now."""
    try:
        subject_id = all_logs[0]['subject_id']
        timestamp = all_logs[0]['timestamp']

        sub_res = supabase.table('subjects')\
            .select('name, subject_code, teacher_id')\
            .eq('subject_id', subject_id).execute()
        if not sub_res.data:
            return

        teacher_data = st.session_state.get('teacher_data', {})
        enrolled_res = supabase.table('subject_students')\
            .select('student_id, students(student_id, name, email)')\
            .eq('subject_id', subject_id).execute()
        enrolled = [n['students'] for n in (enrolled_res.data or []) if n.get('students')]
        if not enrolled:
            st.warning("No enrolled students found for email sending.")
            return

        job_id = enqueue_attendance_emails(
            logs=inserted,
            subject_name=sub_res.data[0]['name'],
            subject_code=sub_res.data[0]['subject_code'],
            teacher_name=teacher_data.get('name', 'Teacher'),
            teacher_email=teacher_data.get('email', '') or '',
            timestamp=timestamp,
            enrolled=enrolled,
        )
        if job_id:
            st.session_state.setdefault("email_job_ids", []).append(job_id)
            st.toast("📧 Emails are being sent in the background.")
    except Exception:
        log.exception("could not queue emails")
        st.warning("⚠️ Attendance saved, but emails could not be queued.")


@st.dialog("Attendance Reports")
def attendance_result_dialog(df, logs):
    show_attendance_result(df, logs)


def _learn_from_confirmed(logs):
    try:
        from src.pipelines.face_learning import commit_confirmed_samples
        n = commit_confirmed_samples(logs)
        if n:
            st.toast(f"🧠 Model learned from {n} confirmed detection(s)", icon="✅")
    except Exception as e:
        print(f"Learning skipped: {e}")
