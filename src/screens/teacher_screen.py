import re
import time
import streamlit as st
import numpy as np
import pandas as pd
from PIL import Image
from datetime import datetime

from src.components.self_learning_ui import show_self_learning_dashboard
from src.components.marks_management import show_teacher_marks
from src.components.ai_insights import (
    show_image_quality_check,
    show_liveness_check,
    show_emotion_analysis,
    show_drowsiness_analysis,
    show_attendance_prediction,
    show_nlp_analytics
)

from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.components.subject_card import subject_card
from src.database.db import (
    check_teacher_exists, create_teacher, teacher_login, teacher_login_checked,
    get_teacher_subjects, get_attendance_for_teacher,
    get_subject_attendance_stats
)
from src.components.dialog_create_subject import create_subject_dialog
from src.components.dialog_share_subject import share_subject_dialog
from src.components.dialog_add_photo import add_photos_dialog
from src.pipelines.face_pipeline import predict_attendance_with_encodings
from src.components.dialog_attendance_results import attendance_result_dialog
from src.components.dialog_voice_attendance import voice_attendance_dialog
from src.components.qr_session import teacher_qr_panel
from src.components.analytics import teacher_analytics_tab
from src.components.ml_risk import show_ml_absence_risk
from src.database.config import supabase
from src.database.attendance_status import eligible
from src.components.attendance_corrections import teacher_attendance_corrections


def teacher_screen():
    style_background_dashboard()
    style_base_layout()

    if "teacher_data" in st.session_state:
        teacher_dashboard()
    elif 'teacher_login_type' not in st.session_state or st.session_state.teacher_login_type == "login":
        teacher_screen_login()
    elif st.session_state.teacher_login_type == "register":
        teacher_screen_register()


def teacher_dashboard():
    teacher_data = st.session_state.teacher_data
    teacher_id = teacher_data["teacher_id"]

    c1, c2 = st.columns(2, vertical_alignment="center", gap="xxlarge")
    with c1:
        header_dashboard()
    with c2:
        teacher_name = teacher_data['name']
        st.subheader(f'Welcome, {teacher_name}')
        if st.button("Logout", type="secondary", key="loginbackbtn", shortcut="control+backspace"):
            st.session_state["is_logged_in"] = False
            del st.session_state.teacher_data
            st.rerun()

    st.space()

    with st.spinner("Loading your subjects.."):
        subjects = get_teacher_subjects(teacher_id)

    if "current_teacher_tab" not in st.session_state:
        st.session_state.current_teacher_tab = "take_attendance"

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Take Attendance",
        "Manage Subjects",
        "Enrolled Students",
        "Attendance Records",
        "Marks",
        "AI Insights",
        "Analytics"
    ])

    tabs = [
        (tab1, "take_attendance",   "Take Attendance",   ":material/photo_camera:"),
        (tab2, "manage_subjects",   "Manage Subjects",   ":material/menu_book:"),
        (tab3, "enrolled_students", "Enrolled Students", ":material/group:"),
        (tab4, "attendance_records","Attendance Records",":material/cards_stack:"),
        (tab5, "marks",             "Marks",             ":material/grade:"),
        (tab6, "ai_insights",       "AI Insights",       ":material/smart_toy:"),
        (tab7, "analytics", "Analytics", ":material/monitoring:"),
    ]
    for tab, key, label, icon in tabs:
        with tab:
            btn_type = "primary" if st.session_state.current_teacher_tab == key else "tertiary"
            if st.button(label, type=btn_type, width="stretch", icon=icon, key=f"tabbtn_{key}"):
                st.session_state.current_teacher_tab = key
                st.rerun()

    st.divider()

    current = st.session_state.current_teacher_tab
    if current == "take_attendance":
        teacher_tab_take_attendance()
    elif current == "manage_subjects":
        teacher_tab_manage_subjects()
    elif current == "enrolled_students":
        teacher_tab_enrolled_students()
    elif current == "attendance_records":
        teacher_tab_attendance_records()
    elif current == "marks":
        show_teacher_marks(subjects, teacher_id)
    elif current == "ai_insights":
        teacher_tab_ai_insights(subjects, teacher_id)
    elif current == "analytics":
        teacher_analytics_tab(subjects, teacher_id)

    footer_dashboard()


def teacher_tab_ai_insights(subjects, teacher_id):
    st.header("AI Insights")

    with st.expander("📧 Send Weekly Parent Reports"):
        st.info("Weekly reports are sent automatically every Monday for the previous Mon–Sun week. "
                "Students already reported for that week are skipped.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Send Weekly Reports Now", type="primary", icon=":material/mail:"):
                from src.services.scheduler import manual_send_weekly_reports
                with st.spinner("Sending weekly reports to all parents..."):
                    success, failed = manual_send_weekly_reports()
                st.success(f"✅ Reports sent! Success: {success}, Failed: {failed}")
        with col2:
            st.metric("Next Auto Send", "Every Monday")
    st.divider()

    if not subjects:
        st.info("Create a subject first to see AI insights.")
        return

    subject_options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    selected_label = st.selectbox("Select Subject", list(subject_options.keys()))

    if selected_label:
        selected_sub = subject_options[selected_label]
        sid = selected_sub["subject_id"]

        enrolled_res = supabase.table("subject_students").select("student_id, students(student_id, name, email)").eq("subject_id", sid).execute()
        enrolled = [n["students"] for n in (enrolled_res.data or []) if n.get("students")]

        logs_res = supabase.table("attendance_logs").select("*").eq("subject_id", sid).execute()
        logs = eligible(logs_res.data)

        st.divider()

        ai_tab1, ai_tab2, ai_tab3, ai_tab4 = st.tabs([
            "Prediction & Risk",
            "Ask Attendance",
            "Emotion & Alertness",
            "Self Learning"
        ])

        with ai_tab1:
            show_attendance_prediction(logs, enrolled)
            st.divider()
            show_ml_absence_risk([s['subject_id'] for s in subjects], logs, enrolled)

        with ai_tab2:
            show_nlp_analytics(logs, enrolled, selected_sub["name"])

        with ai_tab3:
            if st.session_state.get("attendance_images"):
                imgs = [np.array(img.convert("RGB")) if hasattr(img, "convert") else np.array(Image.open(img).convert("RGB")) for img in st.session_state.attendance_images]
                show_emotion_analysis(imgs)
                st.divider()
                show_drowsiness_analysis(imgs)
            else:
                st.info("Upload class photos in Take Attendance tab first.")

        with ai_tab4:
            show_self_learning_dashboard()


def teacher_tab_take_attendance():
    teacher_id = st.session_state.teacher_data['teacher_id']
    st.header('Take AI Attendance')

    if 'attendance_images' not in st.session_state:
        st.session_state.attendance_images = []

    subjects = get_teacher_subjects(teacher_id)

    if not subjects:
        st.warning('You havent created any subjects yet! Please create one to begin!')
        return

    subject_options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}

    col1, col2 = st.columns([3, 1], vertical_alignment='bottom')

    with col1:
        selected_subject_label = st.selectbox(
            'Select Subject',
            options=list(subject_options.keys()),
            key='ai_insights_subject'
        )

    with col2:
        if st.button('Add Photos', type='primary', icon=':material/photo_prints:', width='stretch'):
            add_photos_dialog()

    selected_subject = subject_options[selected_subject_label]
    selected_subject_id = selected_subject["subject_id"]

    st.divider()

    if st.session_state.attendance_images:
        st.header('Added Photos')
        gallery_cols = st.columns(4)

        for idx, img in enumerate(st.session_state.attendance_images):
            with gallery_cols[idx % 4]:
                st.image(img, width='stretch', caption=f'Photo {idx + 1}')

    has_photos = bool(st.session_state.attendance_images)
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button('Clear all photos', width='stretch', type='tertiary', icon=':material/delete:', disabled=not has_photos):
            st.session_state.attendance_images = []
            st.rerun()

    with c2:
        if st.button('Run Face Analysis', width='stretch', type='secondary', icon=':material/analytics:', disabled=not has_photos):
            with st.spinner('Deep scanning classroom photos...'):
                all_detected_ids = {}
                best_conf = {}
                pending = {}

                for idx, img in enumerate(st.session_state.attendance_images):
                    img_np = np.array(img.convert('RGB'))

                    is_good, face_count = show_image_quality_check(img_np)

                    # Anti-spoofing is meaningful for a single-face capture,
                    # not for a group classroom photo.
                    if face_count == 1:
                        if not show_liveness_check(img_np):
                            st.warning(f"Photo {idx + 1}: Spoofing detected! Skipping this photo.")
                            continue

                    detected, _, _, encs = predict_attendance_with_encodings(img_np)

                    for sid, conf in (detected or {}).items():
                        all_detected_ids.setdefault(sid, []).append(f"Photo {idx + 1}")
                        c = conf if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.0
                        best_conf[sid] = max(best_conf.get(sid, 0.0), float(c))
                        if sid in encs and (sid not in pending or c > pending[sid][0]):
                            pending[sid] = (float(c), encs[sid])

                st.session_state.pending_face_samples = pending
                enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', selected_subject_id).execute()
                enrolled_students = enrolled_res.data

                if not enrolled_students:
                    st.warning('No students enrolled in this course')
                else:
                    results, attendance_to_log = [], []
                    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                    for node in enrolled_students:
                        student = node['students']
                        sources = all_detected_ids.get(student['student_id'], [])
                        is_present = len(sources) > 0

                        results.append({
                            "Name": student['name'],
                            "ID": student['student_id'],
                            "Source": ", ".join(sources) if is_present else "-",
                            "Status": "✅ Present" if is_present else "❌ Absent"
                        })

                        attendance_to_log.append({
                            'student_id': student['student_id'],
                            'subject_id': selected_subject_id,
                            'timestamp': current_timestamp,
                            'is_present': bool(is_present),
                            'confidence_score': round(best_conf[student['student_id']], 2) if is_present else None
                        })

                    attendance_result_dialog(pd.DataFrame(results), attendance_to_log)

    with c3:
        if st.button('Use Voice Attendance', type='primary', width='stretch', icon=':material/mic:'):
            voice_attendance_dialog(selected_subject_id)

    st.divider()
    teacher_qr_panel(selected_subject, teacher_id)


def teacher_tab_enrolled_students():
    """Show enrolled students list for each subject"""
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

        res = supabase.table('subject_students')\
            .select('*, students(student_id, name, email, roll_no, section, parent_email)')\
            .eq('subject_id', sid).execute()

        enrolled = [n['students'] for n in (res.data or []) if n.get('students')]

        # ONE query for all students' attendance (was one query per student)
        att_stats = get_subject_attendance_stats(sid)

        st.divider()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Enrolled", len(enrolled))
        with col2:
            with_email = sum(1 for s in enrolled if s.get('email'))
            st.metric("With Email", with_email)
        with col3:
            with_parent = sum(1 for s in enrolled if s.get('parent_email'))
            st.metric("With Parent Email", with_parent)

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
                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                with col1:
                    st.write(f"**{i+1}. {student.get('name', 'Unknown')}**")
                    st.caption(f"Roll No: {student.get('roll_no', 'N/A')} | Section: {student.get('section', 'N/A')}")
                with col2:
                    email = student.get('email', '')
                    st.write(f"📧 {email or 'No email'}")
                with col3:
                    parent = student.get('parent_email', '')
                    st.write(f"👨‍👩‍👧 {parent or 'No parent email'}")
                with col4:
                    s = att_stats.get(student['student_id'], {'total': 0, 'present': 0})
                    total, present = s['total'], s['present']
                    pct   = round((present / total) * 100) if total > 0 else 0
                    color = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"
                    st.write(f"{color} {present}/{total} ({pct}%)")


def teacher_tab_manage_subjects():
    teacher_id = st.session_state.teacher_data['teacher_id']
    col1, col2 = st.columns(2)
    with col1:
        st.header('Manage Subjects', width='stretch')

    with col2:
        if st.button('Create New Subject', width='stretch'):
            create_subject_dialog(teacher_id)

    subjects = get_teacher_subjects(teacher_id)
    if subjects:
        for sub in subjects:
            stats = [
                ("🫂", "Students", sub['total_students']),
                ("🕰️", "Classes", sub['total_classes']),
            ]

            # default-arg binding so each card's button uses ITS OWN subject
            def share_btn(sub=sub):
                if st.button(f"Share Code: {sub['name']}", key=f"share_{sub['subject_code']}", icon=":material/share:"):
                    share_subject_dialog(sub['name'], sub['subject_code'])
                st.space()

            subject_card(
                name=sub['name'],
                code=sub['subject_code'],
                section=sub['section'],
                stats=stats,
                footer_callback=share_btn
            )
    else:
        st.info("NO SUBJECTS FOUND. CREATE ONE ABOVE")


def teacher_tab_attendance_records():
    st.header('Attendance Records')

    teacher_id = st.session_state.teacher_data['teacher_id']
    records = get_attendance_for_teacher(teacher_id)

    if not records:
        st.info("No attendance records yet.")
        return

    data = []
    for r in records:
        ts = r.get('timestamp')
        data.append({
            "ts_group": ts.split(".")[0] if ts else None,
            "Time": datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p") if ts else "N/A",
            "Subject": r['subjects']['name'],
            "Subject Code": r['subjects']['subject_code'],
            "is_present": bool(r.get('is_present', False))
        })

    df = pd.DataFrame(data)

    summary = (
        df.groupby(['ts_group', 'Time', 'Subject', 'Subject Code'])
        .agg(
            Present_Count=('is_present', 'sum'),
            Total_Count=('is_present', 'count')
        ).reset_index()
    )

    summary['Attendance Stats'] = (
        "✅ " + summary['Present_Count'].astype(str) + " /"
        + summary['Total_Count'].astype(str) + ' Students'
    )

    display_df = (summary.sort_values(by='ts_group', ascending=False)
                  [['Time', 'Subject', 'Subject Code', 'Attendance Stats']])

    st.dataframe(display_df, width='stretch', hide_index=True)

    st.divider()
    teacher_attendance_corrections(teacher_id)


def login_teacher(username, password):
    if not username or not password:
        return False

    teacher, lock_msg = teacher_login_checked(username, password)
    if lock_msg:
        st.session_state['teacher_login_error'] = lock_msg

    if teacher:
        status = teacher.get('status') or 'approved'
        if status != 'approved':
            st.session_state['teacher_login_error'] = (
                "Your account is awaiting admin approval." if status == 'pending'
                else "Your account was not approved. Please contact the administrator.")
            return False
        st.session_state.user_role = 'teacher'
        st.session_state.teacher_data = teacher
        st.session_state.is_logged_in = True
        return True

    return False


def teacher_screen_login():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    st.header('Login using password', text_alignment='center')
    st.space()
    st.space()

    teacher_username = st.text_input("Enter username", placeholder='ananyaroy')
    teacher_pass = st.text_input("Enter password", type='password', placeholder="Enter password")

    st.divider()

    btnc1, btnc2 = st.columns(2)

    with btnc1:
        if st.button('Login', icon=':material/passkey:', shortcut='control+enter', width='stretch'):
            if login_teacher(teacher_username, teacher_pass):
                st.toast("welcome back!", icon="👋")
                time.sleep(1)
                st.rerun()
            else:
                st.error(st.session_state.pop('teacher_login_error', None) or "Invalid username and password combo")

    with btnc2:
        if st.button('Register Instead', type="primary", icon=':material/passkey:', width='stretch'):
            st.session_state.teacher_login_type = 'register'
            st.rerun()

    footer_dashboard()


def validate_password(password):
    """Check password strength. Returns (is_valid, error_message)"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 64:
        return False, "Password must not exceed 64 characters."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number (0-9)."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', password):
        return False, "Password must contain at least one special character (!@#$%^&* etc)."
    common_words = ["password", "teacher", "admin", "snapclass", "123456", "qwerty", "letmein"]
    if any(word in password.lower() for word in common_words):
        return False, "Password is too common or contains a dictionary word."
    return True, ""


def register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm, teacher_email=None):
    if not teacher_username or not teacher_name or not teacher_pass:
        return False, "All Fields are required!"
    if check_teacher_exists(teacher_username):
        return False, "Username already taken"
    if teacher_pass != teacher_pass_confirm:
        return False, "Password doesn't match"
    is_valid, pwd_error = validate_password(teacher_pass)
    if not is_valid:
        return False, pwd_error
    # no personal data in password
    lowered = teacher_pass.lower()
    personal = [teacher_username.lower()] + [p.lower() for p in teacher_name.split() if len(p) >= 3]
    if any(p and p in lowered for p in personal):
        return False, "Password must not contain your username or name."
    try:
        create_teacher(teacher_username, teacher_pass, teacher_name, email=teacher_email if teacher_email else None)
        return True, "Registered! An administrator must approve your account before you can log in."
    except Exception as e:
        return False, str(e)


def teacher_screen_register():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    st.header('Register your teacher profile')

    st.space()
    st.space()

    teacher_username = st.text_input("Enter username", placeholder='ananyaroy')
    teacher_name = st.text_input("Enter name", placeholder='Ananya Roy')
    teacher_email = st.text_input("Enter your email", placeholder='teacher@gmail.com', help="Attendance summary will be sent to this email after every class")
    teacher_pass = st.text_input("Enter password", type='password', placeholder="Enter password")
    teacher_pass_confirm = st.text_input("Confirm your password", type='password', placeholder="Enter password")

    st.divider()

    btnc1, btnc2 = st.columns(2)

    with btnc1:
        if st.button('Register now', icon=':material/passkey:', shortcut='control+enter', width='stretch'):
            success, message = register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm, teacher_email)
            if success:
                st.success(message)
                time.sleep(2)
                st.session_state.teacher_login_type = "login"
                st.rerun()
            else:
                st.error(message)

    with btnc2:
        if st.button('Login Instead', type="primary", icon=':material/passkey:', width='stretch'):
            st.session_state.teacher_login_type = 'login'
            st.rerun()

    footer_dashboard()
