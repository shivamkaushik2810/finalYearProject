import streamlit as st
from src.database.db import create_attendance
from src.database.config import supabase
from src.services.email_service import send_all_attendance_emails
import time


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
            try:
                create_attendance(logs)
                st.toast("✅ Attendance saved!")
                _learn_from_confirmed(logs)
                _send_emails(logs)
                st.session_state.attendance_images = []
                st.session_state.voice_attendance_results = None
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f'Error saving attendance: {str(e)}')


def _send_emails(logs):
    try:
        if not logs:
            return

        subject_id = logs[0]['subject_id']
        timestamp  = logs[0]['timestamp']

        sub_res = supabase.table('subjects')\
            .select('name, subject_code, teacher_id')\
            .eq('subject_id', subject_id).execute()
        if not sub_res.data:
            return

        subject_name = sub_res.data[0]['name']
        subject_code = sub_res.data[0]['subject_code']

        teacher_data  = st.session_state.get('teacher_data', {})
        teacher_name  = teacher_data.get('name', 'Teacher')
        teacher_email = teacher_data.get('email', '')

        enrolled_res = supabase.table('subject_students')\
            .select('student_id, students(student_id, name, email)')\
            .eq('subject_id', subject_id).execute()

        all_enrolled = [
            node['students']
            for node in (enrolled_res.data or [])
            if node.get('students')
        ]

        if not all_enrolled:
            st.warning("No enrolled students found for email sending.")
            return

        with st.spinner("📧 Sending emails to students and teacher..."):
            ok, fail, teacher_ok = send_all_attendance_emails(
                logs=logs,
                subject_name=subject_name,
                subject_code=subject_code,
                teacher_name=teacher_name,
                teacher_email=teacher_email,
                timestamp=timestamp,
                all_enrolled_students=all_enrolled,
            )

        if ok > 0:
            st.toast(f"📧 Emails sent to {ok} student(s)!", icon="✅")
        if fail > 0:
            st.warning(f"⚠️ {fail} student email(s) could not be sent (no email on file).")
        if teacher_ok:
            st.toast("📊 Summary email sent to teacher!", icon="✅")
        elif teacher_email == '':
            st.info("ℹ️ No teacher email on file — summary not sent.")

    except Exception as e:
        st.warning(f"⚠️ Attendance saved but email failed: {str(e)}")


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
