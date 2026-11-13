from src.components.filters import subject_label
from types import SimpleNamespace as _NS
from src.database.db import get_subject_logs_full
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

import logging
from src.services import attendance_stats as S
from src.components.charts import attendance_trend, subject_bars
from src.ui.widgets import empty_state, stat_cards

_log = logging.getLogger(__name__)

TEACHER_NAV = {
    "overview": ":material/dashboard: Overview",
    "take_attendance": ":material/photo_camera: Attendance",
    "manage_subjects": ":material/menu_book: Subjects",
    "enrolled_students": ":material/group: Students",
    "attendance_records": ":material/cards_stack: Records",
    "marks": ":material/grade: Marks",
    "ai_insights": ":material/smart_toy: Insights",
    "analytics": ":material/monitoring: Analytics",
}


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
        if st.button("Log out", type="secondary", key="danger_logout", shortcut="control+backspace"):
            st.session_state["is_logged_in"] = False
            del st.session_state.teacher_data
            st.rerun()

    st.space()

    with st.spinner("Loading your subjects.."):
        subjects = get_teacher_subjects(teacher_id)

    # one navigation row. The state key is the same one other code already uses.
    if st.session_state.get("current_teacher_tab") not in TEACHER_NAV:
        st.session_state.current_teacher_tab = st.session_state.get("_last_teacher_tab") or "overview"
    picked = st.segmented_control(
        "Section", list(TEACHER_NAV), format_func=TEACHER_NAV.get,
        key="current_teacher_tab", label_visibility="collapsed",
    )
    if picked:
        st.session_state["_last_teacher_tab"] = picked

    st.divider()

    current = picked or st.session_state.get("_last_teacher_tab") or "overview"
    if current == "overview":
        teacher_tab_overview(subjects)
    elif current == "take_attendance":
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

    from src.components.feedback import show_feedback_section
    show_feedback_section("teacher", teacher_id, teacher_name)

    footer_dashboard()


def _goto_tab(tab):
    st.session_state.current_teacher_tab = tab


def _load_subject_logs(subjects):
    """{subject_id: eligible logs}. Same helpers as AI Insights, so the numbers match."""
    out, failed = {}, []
    for s in subjects:
        sid = s["subject_id"]
        try:
            out[sid] = eligible(get_subject_logs_full(sid)) or []
        except Exception:
            _log.exception("Could not load attendance logs for subject_id=%s", sid)
            failed.append(s["name"])
    return out, failed


def _subject_pct_map(subjects):
    logs_by_sid, _ = _load_subject_logs(subjects)
    result = {}
    for sid, rows in logs_by_sid.items():
        t = S.overall(rows)
        result[sid] = (t["pct"], t["total"])
    return result


def teacher_tab_overview(subjects):
    st.header("Overview")
    if not subjects:
        empty_state("Create your first subject", "Subjects hold your students, attendance and marks.")
        st.button("Create subject", type="primary", on_click=_goto_tab, args=("manage_subjects",))
        return

    st.button("Take attendance now", type="primary", icon=":material/photo_camera:",
              on_click=_goto_tab, args=("take_attendance",))

    with st.spinner("Loading attendance..."):
        logs_by_sid, failed = _load_subject_logs(subjects)
    if failed:
        st.warning("Couldn't load attendance for: " + ", ".join(failed) + ". The numbers below leave them out.")

    all_logs = [dict(row, subject_id=sid) for sid, rows in logs_by_sid.items() for row in rows]
    total = S.overall(all_logs)
    at_risk = len(S.at_risk_students(all_logs))
    last = pd.to_datetime(S.last_session(all_logs), errors="coerce")
    last_txt = "None yet" if pd.isna(last) else f"{last:%d %b, %I:%M %p}"
    tone = ("" if not total["total"] else "good" if total["pct"] >= 75
            else "avg" if total["pct"] >= 50 else "bad")
    stat_cards([
        ("Subjects", len(subjects), ""),
        ("Average attendance", f"{total['pct']:.0f}%" if total["total"] else "No data", tone),
        ("At-risk students", at_risk, "bad" if at_risk else "good"),
        ("Last session", last_txt, ""),
    ])

    cols = st.columns(2)
    chart_rows = []
    for i, sub in enumerate(subjects):
        loaded = sub["subject_id"] in logs_by_sid  # a subject that failed to load shows no numbers
        t = S.overall(logs_by_sid.get(sub["subject_id"], []))
        if loaded:
            chart_rows.append((sub["name"], t["pct"]))
        with cols[i % 2]:
            subject_card(
                name=sub["name"], code=sub["subject_code"], section=sub["section"],
                course=sub.get("course"), year=sub.get("year"),
                stats=[("\U0001FAC2", "Students", sub["total_students"]),
                       ("\U0001F570\uFE0F", "Classes", sub["total_classes"])],
                pct=t["pct"] if loaded else None, total=t["total"] if loaded else None,
            )

    c1, c2 = st.columns(2)
    with c1:
        subject_bars(chart_rows)
    with c2:
        attendance_trend(all_logs)


def _password_checks(pw, username="", name=""):
    """Checklist that mirrors validate_password below, so the hints never disagree with the rules."""
    pw = pw or ""
    low = pw.lower()
    personal = [p for p in [(username or "").lower()] + [w.lower() for w in (name or "").split() if len(w) >= 3] if p]
    _, msg = validate_password(pw)
    predictable = msg.startswith(("Password is too common", "Password must not repeat",
                                  "Password must not contain predictable"))
    return [
        (8 <= len(pw) <= 64, "8 to 64 characters"),
        (bool(re.search(r"[A-Z]", pw)), "An uppercase letter"),
        (bool(re.search(r"[a-z]", pw)), "A lowercase letter"),
        (bool(re.search(r"[0-9]", pw)), "A number"),
        (bool(re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', pw)), "A special character"),
        (bool(pw) and not predictable, "No common words, repeats or sequences like 1234"),
        (bool(pw) and not any(p in low for p in personal), "Doesn't contain your username or name"),
    ]


def _render_password_checklist(pw, username="", name=""):
    if not pw:
        return
    checks = _password_checks(pw, username, name)
    score = sum(1 for ok, _ in checks if ok)
    label = "Strong" if score == len(checks) else "Fair" if score >= 5 else "Weak"
    color = {"Strong": "#3B6D11", "Fair": "#BA7517", "Weak": "#A32D2D"}[label]
    segs = "".join(f'<i style="background:{color if n < score else "#cbd5e1"}"></i>' for n in range(len(checks)))
    tick, cross = "\u2713", "\u2717"
    lines = "<br>".join(f"{tick if ok else cross} {text}" for ok, text in checks)
    st.markdown(f'<div class="sc-pw" role="img" aria-label="Password strength: {label}">{segs}</div>'
                f'<div style="font-size:.85rem"><b>{label}</b><br>{lines}</div>', unsafe_allow_html=True)


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
                if success == 0 and failed == 0:
                    st.info("Nothing to send: no classes last week, no parent emails, "
                            "or every parent already received this week's report.")
                elif failed:
                    st.warning(f"Sent: {success}, failed: {failed}. Failed ones retry on the next run.")
                else:
                    st.success(f"✅ Sent {success} report(s).")
        with col2:
            st.metric("Next Auto Send", "Every Monday")
    st.divider()

    with st.expander("🚨 Defaulter Students — Email Parents"):
        from src.components.defaulter_emails import show_defaulter_email_panel
        show_defaulter_email_panel(teacher_id=teacher_id, key="teacher_def")
    st.divider()

    if not subjects:
        st.info("Create a subject first to see AI insights.")
        return

    subject_options = {subject_label(s): s for s in subjects}
    selected_label = st.selectbox("Select Subject", list(subject_options.keys()))

    if selected_label:
        selected_sub = subject_options[selected_label]
        sid = selected_sub["subject_id"]

        enrolled_res = supabase.table("subject_students").select("student_id, students(student_id, name, email)").eq("subject_id", sid).execute()
        enrolled = [n["students"] for n in (enrolled_res.data or []) if n.get("students")]

        logs_res = _NS(data=get_subject_logs_full(sid))
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
    st.header('Take Attendance')

    subjects = get_teacher_subjects(teacher_id)
    if not subjects:
        st.warning('You havent created any subjects yet! Please create one to begin!')
        return

    subject_options = {subject_label(s): s for s in subjects}
    selected_label = st.selectbox('Select Subject', options=list(subject_options.keys()),
                                  key='ai_insights_subject')

    from src.components.attendance_hub import attendance_hub
    attendance_hub(subject_options[selected_label], teacher_id)


def teacher_tab_enrolled_students():
    from src.components.class_filters_ui import teacher_tab_enrolled_students as _impl
    _impl()

def teacher_tab_manage_subjects():
    teacher_id = st.session_state.teacher_data['teacher_id']
    col1, col2 = st.columns(2)
    with col1:
        st.header('Manage Subjects', width='stretch')

    with col2:
        if st.button('Create New Subject', width='stretch'):
            create_subject_dialog(teacher_id)

    subjects = get_teacher_subjects(teacher_id)
    pct_map = _subject_pct_map(subjects) if subjects else {}
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
                section=sub['section'], course=sub.get('course'), year=sub.get('year'),
                stats=stats,
                footer_callback=share_btn,
                pct=pct_map.get(sub['subject_id'], (None, None))[0],
                total=pct_map.get(sub['subject_id'], (None, None))[1]
            )
    else:
        st.info("NO SUBJECTS FOUND. CREATE ONE ABOVE")


def teacher_tab_attendance_records():
    from src.components.class_filters_ui import teacher_tab_attendance_records as _impl
    _impl()

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
    _render_password_checklist(teacher_pass, teacher_username, teacher_name)
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
