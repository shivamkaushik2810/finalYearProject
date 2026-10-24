import streamlit as st

from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.components.student_attendance_list import show_student_attendance_list
from PIL import Image
import numpy as np
from src.pipelines.face_pipeline import predict_attendance, get_face_embeddings, train_classifier
from src.pipelines.voice_pipeline import get_voice_embedding
from src.pipelines.liveness_detection import detect_screen_or_photo, check_face_quality
from src.database.db import get_student_by_id, get_all_students, create_student, get_student_subjects, get_student_attendance, unenroll_student_to_subject
from src.services.otp_service import send_and_save_otp, verify_otp, is_email_verified, mark_email_verified
from src.services.email_rules import emails_conflict, is_valid_email
from src.services.parent_email_rules import validate_parent_email
import time
from src.components.liveness_challenge import run_liveness_challenge

from src.components.dialog_enroll import enroll_dialog
from src.components.subject_card import subject_card
from src.components.marks_management import show_student_marks
from src.components.child_overview import render_child_overview, render_announcements
from src.components.qr_session import student_qr_panel
from src.components.timetable import render_timetable


def student_dashboard():
    student_data = st.session_state.student_data
    student_id   = student_data['student_id']

    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"Welcome, {student_data['name']}")
        if st.button("Logout", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['is_logged_in'] = False
            del st.session_state.student_data
            st.rerun()

    st.space()

    if st.query_params.get('qr-code'):
        student_qr_panel(student_data, key_prefix='qr_top')
        st.divider()

    tab_over, tab1, tab2, tab3 = st.tabs(['🏠 Overview', '📚 My Subjects', '📋 My Attendance', '📝 My Marks'])

    with tab_over:
        student_qr_panel(student_data, key_prefix='qr_ov')
        st.divider()
        render_child_overview(student_id, viewer='student')
        st.divider()
        render_announcements(student_id, viewer='student')
        st.divider()
        render_timetable(student_id)

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.header('Your Enrolled Subjects')
        with c2:
            if st.button('Enroll in Subject', type='primary', width='stretch'):
                enroll_dialog()

        st.divider()

        with st.spinner('Loading your enrolled subjects..'):
            subjects = get_student_subjects(student_id)
            logs     = get_student_attendance(student_id)

        stats_map = {}
        for log in logs:
            sid = log['subject_id']
            if sid not in stats_map:
                stats_map[sid] = {"total": 0, "attended": 0}
            stats_map[sid]['total'] += 1
            if log.get('is_present'):
                stats_map[sid]['attended'] += 1

        if not subjects:
            st.info("Not enrolled in any subject yet. Click 'Enroll in Subject'.")
        else:
            cols = st.columns(2)
            for i, sub_node in enumerate(subjects):
                sub   = sub_node['subjects']
                sid   = sub['subject_id']
                stats = stats_map.get(sid, {"total": 0, "attended": 0})

                def unenroll_button():
                    if st.button("Unenroll from this course", type='tertiary',
                                 width='stretch', icon=':material/delete_forever:',
                                 key=f'unenroll_{sid}'):
                        unenroll_student_to_subject(student_id, sid)
                        st.toast(f"Unenrolled from {sub['name']} successfully!")
                        st.rerun()

                with cols[i % 2]:
                    subject_card(
                        name=sub['name'],
                        code=sub['subject_code'],
                        section=sub['section'], course=sub.get('course'), year=sub.get('year'),
                        stats=[
                            ('📅', 'Total',    stats['total']),
                            ('✅', 'Attended', stats['attended']),
                        ],
                        footer_callback=unenroll_button
                    )

    with tab2:
        show_student_attendance_list(student_id)

    with tab3:
        show_student_marks(student_id)

    footer_dashboard()


def _otp_verify_section(email, purpose, label, name="User"):
    is_verified = is_email_verified(email, purpose)
    if is_verified:
        st.success(f"✅ {label} verified!")
        return True

    col1, col2 = st.columns([2, 1])
    with col1:
        otp_input = st.text_input(
            f"Enter OTP sent to {email}",
            max_chars=6, placeholder="6-digit OTP",
            key=f"otp_{purpose}"
        )
    with col2:
        st.write("")
        st.write("")
        if st.button(f"Send OTP", key=f"send_otp_{purpose}", type="secondary"):
            if email and "@" in email:
                with st.spinner(f"Sending OTP to {email}..."):
                    try:
                        send_and_save_otp(email, purpose, name)
                        st.success(f"✅ OTP sent to {email}!")
                    except Exception as e:
                        st.error(f"Failed: {str(e)}")
            else:
                st.warning("Please enter a valid email first!")

    if otp_input and len(otp_input) == 6:
        if st.button(f"Verify OTP", key=f"verify_{purpose}", type="primary"):
            is_valid, message = verify_otp(email, otp_input, purpose)
            if is_valid:
                mark_email_verified(email, purpose)
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    return False


def student_screen():
    style_background_dashboard()
    style_base_layout()

    if "student_data" in st.session_state:
        student_dashboard()
        return

    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn',
                     shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    st.header('Login using FaceID', text_alignment='center')
    st.space()
    st.space()

    show_registration = False
    photo_source = st.camera_input("Position your face in the center")

    if photo_source:
        img = np.array(Image.open(photo_source).convert('RGB'))

        with st.spinner('AI is scanning..'):
            is_real, reason = detect_screen_or_photo(img)
            if not is_real:
                st.error(f"❌ {reason}")
                st.warning("Please show your real face — not a phone screen or photo!")
            else:
                detected, all_ids, num_faces = predict_attendance(img)

                if num_faces == 0:
                    st.warning('Face not found! Position your face clearly.')
                elif num_faces > 1:
                    st.warning('Multiple faces found! One person only.')
                else:
                    if detected:
                        student_id   = list(detected.keys())[0]
                        from src.database.students_query import get_student_by_id
                        student = get_student_by_id(student_id)
                        if student:
                            st.session_state.pending_student = student
                            st.session_state.pending_frontal = img
                    else:
                        st.info('Face not recognized! You might be a new student!')
                        show_registration = True

    if not photo_source:
        for k in ('pending_student', 'pending_frontal', 'liveness_task',
                  'liveness_passed', 'liveness_attempt', 'liveness_steps',
                  'liveness_idx', 'liveness_start', 'liveness_fails'):
            st.session_state.pop(k, None)

    if st.session_state.get('pending_student') and not show_registration:
        if run_liveness_challenge(st.session_state.pending_frontal):
            student = st.session_state.pop('pending_student')
            st.session_state.pop('pending_frontal', None)
            st.session_state.pop('liveness_task', None)
            st.session_state.pop('liveness_passed', None)
            st.session_state.is_logged_in = True
            st.session_state.user_role    = 'student'
            st.session_state.student_data = student
            st.toast(f"Welcome Back {student['name']}")
            time.sleep(1)
            st.rerun()

    if show_registration:
        with st.container(border=True):
            st.header('Register new Profile')

            st.subheader('👤 Personal Information')
            col1, col2 = st.columns(2)
            with col1:
                new_name  = st.text_input("Full Name *", placeholder='E.g. student Name')
                new_email = st.text_input("Your Email *", placeholder='E.g. student@gmail.com')

            with col2:
                new_roll    = st.text_input("Roll Number *", placeholder='E.g. 123456789')
                new_section = st.selectbox("Section *", options=['A','B','C','D','E','F'])

            course_col, year_col = st.columns(2)
            with course_col:
                new_course = st.selectbox("Course *", options=['B.Tech','M.Tech','MCA','BCA','MBA','B.Sc','M.Sc'])

            with year_col:
                new_year = st.selectbox("Year *", options=['1','2','3','4'])


            if new_email and "@" in new_email:
                st.write("**Verify Your Email:**")
                student_verified = _otp_verify_section(
                    new_email, "student_email", "Student email", new_name or "Student"
                )
            else:
                student_verified = False

            st.divider()
            st.subheader('👨‍👩‍👧 Parent / Guardian Information')
            col3, col4 = st.columns(2)
            with col3:
                parent_name  = st.text_input("Parent Name *", placeholder='E.g. Parent Name')
            with col4:
                parent_email = st.text_input("Parent Email *", placeholder='E.g. parent@gmail.com')

            st.info("📧 Weekly attendance report sent to parent every Monday")

            email_conflict = emails_conflict(new_email, parent_email)
            if email_conflict:
                st.error("❌ Parent email must be different from your own email. Enter your parent or guardian email.")
            if parent_email and "@" in parent_email and not email_conflict:
                st.write("**Verify Parent Email:**")
                parent_verified = _otp_verify_section(
                    parent_email, "parent_email", "Parent email", parent_name or "Parent"
                )
            else:
                parent_verified = False

            st.divider()
            st.subheader('🎤 Optional: Voice Enrollment')
            st.info("Enroll your voice for voice only attendance")
            audio_data = None
            try:
                audio_data = st.audio_input('Record: I am present, My name is Shivam.')
            except Exception:
                st.error('Audio input failed!')

            st.divider()
            col_s, col_p = st.columns(2)
            with col_s:
                if student_verified:
                    st.success("✅ Student email verified")
                else:
                    st.warning("⚠️ Student email not verified")
            with col_p:
                if parent_verified:
                    st.success("✅ Parent email verified")
                else:
                    st.warning("⚠️ Parent email not verified")

            if st.button('Create Account', type='primary', width='stretch'):
                if not new_name:
                    st.error('Please enter your full name!')
                elif not new_roll:
                    st.error('Please enter your roll number!')
                elif not new_email:
                    st.error('Please enter your email!')
                elif not parent_email:
                    st.error('Please enter parent email!')
                elif not validate_parent_email(new_email, parent_email)[0]:
                    st.error(validate_parent_email(new_email, parent_email)[1])
                elif not is_valid_email(new_email) or not is_valid_email(parent_email):
                    st.error('Please enter valid email addresses!')
                elif emails_conflict(new_email, parent_email):
                    st.error('❌ Parent email must be different from the student email!')
                elif not student_verified:
                    st.error('❌ Please verify your student email first!')
                elif not parent_verified:
                    st.error('❌ Please verify parent email first!')
                else:
                    with st.spinner('Creating profile..'):
                        img       = np.array(Image.open(photo_source).convert('RGB'))
                        encodings = get_face_embeddings(img)
                        if encodings:
                            face_emb  = encodings[0].tolist()
                            voice_emb = None
                            if audio_data:
                                voice_emb = get_voice_embedding(audio_data.read())
                            response_data = create_student(
                                new_name,
                                face_embedding  = face_emb,
                                voice_embedding = voice_emb,
                                email           = new_email,
                                roll_no         = new_roll,
                                section         = new_section,
                                parent_email    = parent_email,
                                parent_name     = parent_name,
                                year            = new_year,
                                course          = new_course
                            )
                            if response_data:
                                train_classifier()
                                st.session_state.is_logged_in = True
                                st.session_state.user_role    = 'student'
                                st.session_state.student_data = response_data[0]
                                st.toast(f'Profile Created! Hi {new_name}!')
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error('Could not capture facial features. Try again!')

    footer_dashboard()
