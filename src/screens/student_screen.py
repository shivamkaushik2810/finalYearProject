import streamlit as st
from src.components.parent_email_update import show_parent_email_update

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
from src.components.published_timetable_ui import show_student_timetable
from src.components.leave_ui import student_leave_tab
from src.components.dialog_add_angles import add_angles_dialog
from src.services.face_embeddings import all_embeddings
from src.ui.portal_theme import inject_portal_theme


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
    show_parent_email_update(student_data)

    if len(all_embeddings(student_data)) < 3:
        st.warning("📸 Add at least 3 face angles (front, left, right) so you are recognised reliably.")
        if st.button('Add face angles now', type='primary', key='add_angles_banner'):
            add_angles_dialog(student_id)

    if st.query_params.get('qr-code'):
        student_qr_panel(student_data, key_prefix='qr_top')
        st.divider()

    from src.components.student_portal_nav import student_sidebar, student_timetable_section
    section = student_sidebar(student_data)

    if section == 'overview':
        student_qr_panel(student_data, key_prefix='qr_ov')
        st.divider()
        render_child_overview(student_id, viewer='student')
        st.divider()
        render_announcements(student_id, viewer='student')
        st.divider()
        show_student_timetable(student_data)


    if section == 'subjects':
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

        from src.services.attendance_summary import summarize
        stats_map = {}
        for sid in {l['subject_id'] for l in logs if l.get('subject_id')}:
            v = summarize([l for l in logs if l.get('subject_id') == sid])
            stats_map[sid] = {'total': v['total'], 'attended': v['present'], 'pct': v['pct']}

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
                        footer_callback=unenroll_button,
                        pct=stats.get('pct'),
                        total=stats['total'],
                    )


    if section == 'attendance':
        show_student_attendance_list(student_id)


    if section == 'marks':
        show_student_marks(student_id)


    if section == 'leave':
        try:
            student_leave_tab(student_id)
        except Exception as e:
            print(f"Leave tab error: {type(e).__name__}")
            st.info("Leave requests are not available yet (database setup missing).")


    if section == 'timetable':
        student_timetable_section(student_data)

    from src.components.feedback import show_feedback_section
    show_feedback_section("student", student_id, student_data["name"])

    footer_dashboard()


OTP_RESEND_SECONDS = 30
REG_STEPS = ["Personal", "Verify email", "Parent", "Voice"]
_REG_SECTIONS = ['A', 'B', 'C', 'D', 'E', 'F']
_REG_COURSES = ['B.Tech', 'M.Tech', 'MCA', 'BCA', 'MBA', 'B.Sc', 'M.Sc']
_REG_YEARS = ['1', '2', '3', '4']
_REG_KEYS = ("reg", "reg_step", "reg_errs")


def _otp_verify_section(email, purpose, label, name="User"):
    if is_email_verified(email, purpose):
        st.success(f"✅ {label} verified!")
        return True

    sent_key = f"otp_sent_at_{purpose}_{email}"
    col1, col2 = st.columns([2, 1], vertical_alignment="bottom")
    with col1:
        otp_input = st.text_input(
            f"Enter the 6-digit code sent to {email}",
            max_chars=6, placeholder="6-digit OTP",
            key=f"otp_{purpose}"
        )
    with col2:
        sent_at = st.session_state.get(sent_key)
        if st.button("Resend code" if sent_at else "Send code", key=f"send_otp_{purpose}", type="secondary"):
            wait = OTP_RESEND_SECONDS - (time.time() - sent_at) if sent_at else 0
            if wait > 0:
                st.warning(f"You can request a new code in {int(wait) + 1} seconds.")
            elif not (email and "@" in email):
                st.warning("Please enter a valid email first!")
            else:
                with st.spinner(f"Sending OTP to {email}..."):
                    try:
                        send_and_save_otp(email, purpose, name)
                        st.session_state[sent_key] = time.time()
                        st.success(f"✅ OTP sent to {email}!")
                    except ValueError as e:      # cooldown or hourly limit reported by the OTP service
                        st.warning(str(e))
                    except Exception:
                        st.error("Couldn't send the code. Check the email address and try again.")

    if otp_input and len(otp_input) == 6:
        if st.button("Verify OTP", key=f"verify_{purpose}", type="primary"):
            is_valid, message = verify_otp(email, otp_input, purpose)
            if is_valid:
                mark_email_verified(email, purpose)
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    return False


def _reg_field_error(errs, field):
    if errs.get(field):
        st.caption(f":red[{errs[field]}]")


def _reg_problem(reg):
    """First problem with the registration data, or None. The same checks the old single form made."""
    if not reg.get("name"):
        return "Please enter your full name!"
    if not reg.get("roll"):
        return "Please enter your roll number!"
    if not reg.get("email"):
        return "Please enter your email!"
    if not reg.get("parent_email"):
        return "Please enter parent email!"
    ok, msg = validate_parent_email(reg["email"], reg["parent_email"])
    if not ok:
        return msg
    if not is_valid_email(reg["email"]) or not is_valid_email(reg["parent_email"]):
        return "Please enter valid email addresses!"
    if emails_conflict(reg["email"], reg["parent_email"]):
        return "Parent email must be different from the student email!"
    if not is_email_verified(reg["email"], "student_email"):
        return "Please verify your student email first!"
    if not is_email_verified(reg["parent_email"], "parent_email"):
        return "Please verify parent email first!"
    return None


def _registration_wizard(photo_source):
    """Guided registration: Personal, Verify email, Parent, Voice. Every check of the old form is still made."""
    from src.ui.widgets import stepper
    reg = st.session_state.setdefault("reg", {})
    step = st.session_state.setdefault("reg_step", 1)
    errs = st.session_state.get("reg_errs", {})

    with st.container(border=True):
        st.header('Register new Profile')
        stepper(REG_STEPS, step)

        if step == 1:
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Full Name *", value=reg.get("name", ""), placeholder='E.g. student Name', key="reg_name")
                _reg_field_error(errs, "name")
                email = st.text_input("Your Email *", value=reg.get("email", ""), placeholder='E.g. student@gmail.com', key="reg_email")
                _reg_field_error(errs, "email")
            with col2:
                roll = st.text_input("Roll Number *", value=reg.get("roll", ""), placeholder='E.g. 123456789', key="reg_roll")
                _reg_field_error(errs, "roll")
                section = st.selectbox("Section *", options=_REG_SECTIONS,
                                       index=_REG_SECTIONS.index(reg.get("section", "A")), key="reg_section")
            course_col, year_col = st.columns(2)
            with course_col:
                course = st.selectbox("Course *", options=_REG_COURSES,
                                      index=_REG_COURSES.index(reg.get("course", _REG_COURSES[0])), key="reg_course")
            with year_col:
                year = st.selectbox("Year *", options=_REG_YEARS,
                                    index=_REG_YEARS.index(reg.get("year", "1")), key="reg_year")
            if st.button("Continue", type="primary", key="reg_next_1"):
                reg.update(name=name.strip(), email=email.strip(), roll=roll.strip(),
                           section=section, course=course, year=year)
                e = {}
                if not reg["name"]:
                    e["name"] = "Please enter your full name!"
                if not reg["roll"]:
                    e["roll"] = "Please enter your roll number!"
                if not reg["email"]:
                    e["email"] = "Please enter your email!"
                elif not is_valid_email(reg["email"]):
                    e["email"] = "Please enter a valid email address!"
                st.session_state["reg_errs"] = e
                if not e:
                    st.session_state["reg_step"] = 2
                st.rerun()

        elif step == 2:
            st.write(f"We will verify **{reg['email']}** so you can receive attendance emails.")
            verified = _otp_verify_section(reg["email"], "student_email", "Student email", reg.get("name") or "Student")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_2"):
                    st.session_state["reg_step"] = 1
                    st.rerun()
            with b2:
                if st.button("Continue", type="primary", key="reg_next_2"):
                    if verified or is_email_verified(reg["email"], "student_email"):
                        st.session_state["reg_errs"] = {}
                        st.session_state["reg_step"] = 3
                    else:
                        st.session_state["reg_errs"] = {"otp": "Please verify your student email first!"}
                    st.rerun()
            _reg_field_error(errs, "otp")

        elif step == 3:
            col3, col4 = st.columns(2)
            with col3:
                pname = st.text_input("Parent Name *", value=reg.get("parent_name", ""), placeholder='E.g. Parent Name', key="reg_pname")
                _reg_field_error(errs, "parent_name")
            with col4:
                pemail = st.text_input("Parent Email *", value=reg.get("parent_email", ""), placeholder='E.g. parent@gmail.com', key="reg_pemail")
                _reg_field_error(errs, "parent_email")
            st.info("📧 Weekly attendance report sent to parent every Monday")
            pemail = pemail.strip()
            conflict = bool(pemail) and emails_conflict(reg["email"], pemail)
            if conflict:
                st.error("❌ Parent email must be different from your own email. Enter your parent or guardian email.")
            if pemail and "@" in pemail and not conflict:
                _otp_verify_section(pemail, "parent_email", "Parent email", pname or "Parent")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_3"):
                    reg.update(parent_name=pname.strip(), parent_email=pemail)
                    st.session_state["reg_step"] = 2
                    st.rerun()
            with b2:
                if st.button("Continue", type="primary", key="reg_next_3"):
                    reg.update(parent_name=pname.strip(), parent_email=pemail)
                    e = {}
                    if not reg["parent_name"]:
                        e["parent_name"] = "Please enter your parent's name!"
                    if not pemail:
                        e["parent_email"] = "Please enter parent email!"
                    elif not is_valid_email(pemail):
                        e["parent_email"] = "Please enter valid email addresses!"
                    elif emails_conflict(reg["email"], pemail):
                        e["parent_email"] = "Parent email must be different from the student email!"
                    else:
                        ok, msg = validate_parent_email(reg["email"], pemail)
                        if not ok:
                            e["parent_email"] = msg
                        elif not is_email_verified(pemail, "parent_email"):
                            e["parent_email"] = "Please verify parent email first!"
                    st.session_state["reg_errs"] = e
                    if not e:
                        st.session_state["reg_step"] = 4
                    st.rerun()

        else:
            st.subheader('🎤 Optional: Voice Enrollment')
            st.info("Enroll your voice for voice only attendance. You can skip this step.")
            audio_data = None
            try:
                audio_data = st.audio_input('Record: "I am present, my name is ..." (say your own name)')
            except Exception:
                st.error('Audio input failed! You can skip this step.')
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_4"):
                    st.session_state["reg_step"] = 3
                    st.rerun()
            with b2:
                create_clicked = st.button('Create Account', type='primary', key="reg_create")
            if create_clicked:
                problem = _reg_problem(reg)
                if problem:
                    st.error(f"❌ {problem}")
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
                                reg["name"],
                                face_embedding  = face_emb,
                                voice_embedding = voice_emb,
                                email           = reg["email"],
                                roll_no         = reg["roll"],
                                section         = reg["section"],
                                parent_email    = reg["parent_email"],
                                parent_name     = reg["parent_name"],
                                year            = reg["year"],
                                course          = reg["course"]
                            )
                            if response_data:
                                train_classifier()
                                for k in _REG_KEYS:
                                    st.session_state.pop(k, None)
                                st.session_state.is_logged_in = True
                                st.session_state.user_role    = 'student'
                                st.session_state.student_data = response_data[0]
                                st.toast(f"Profile Created! Hi {response_data[0].get('name', '')}!")
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error('Could not capture facial features. Try again!')


def student_screen():
    style_background_dashboard()
    style_base_layout()
    inject_portal_theme()

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
                  'liveness_idx', 'liveness_start', 'liveness_fails',
                  'reg', 'reg_step', 'reg_errs'):
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
        _registration_wizard(photo_source)

    footer_dashboard()
