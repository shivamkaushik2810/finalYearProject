import time
import streamlit as st
from src.database.config import supabase
from src.database.db import enroll_student_to_subject, find_subject_for_student
from src.components.filters import can_enroll, class_label
from src.components.dialog_enroll import _fresh_student


def _close():
    st.query_params.clear()
    st.rerun()


@st.dialog("Quick Enrollment")
def auto_enroll_dialog(subject_code):
    student = _fresh_student(st.session_state.student_data)
    student_id = student['student_id']

    subject = find_subject_for_student(subject_code, student)
    if not subject:
        st.error('Subject Code not found!')
        if st.button('Close'):
            _close()
        return

    check = supabase.table('subject_students').select('*')\
        .eq('subject_id', subject['subject_id']).eq('student_id', student_id).execute()
    if check.data:
        st.info("You're already enrolled!")
        if st.button('Got it!'):
            _close()
        return

    allowed, why = can_enroll(subject, student)
    if not allowed:
        st.error(f"🚫 {why}")
        if st.button('Close'):
            _close()
        return

    st.markdown(f"Would you like to enroll in **{subject['name']}** ({class_label(subject)})?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button('No thanks'):
            _close()
    with c2:
        if st.button('Yes enroll now!', type='primary', width='stretch'):
            ok = False
            try:
                enroll_student_to_subject(student_id, subject['subject_id'])
                ok = True
            except ValueError as e:
                st.error(f"🚫 {e}")
            except Exception as e:
                st.error(f"Could not enroll: {e}")
            if ok:
                st.success('Joined successfully!')
                st.query_params.clear()
                time.sleep(2)
                st.rerun()
