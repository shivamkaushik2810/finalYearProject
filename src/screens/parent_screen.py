import streamlit as st
import time

from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.database.db import get_children_for_parent
from src.components.timetable import render_timetable
from src.services.otp_service import send_and_save_otp, verify_otp
from src.components.child_overview import (
    render_child_overview, render_attendance_history,
    render_marks, render_announcements
)

OTP_PURPOSE = "parent_login"


def parent_screen():
    style_background_dashboard()
    style_base_layout()

    if "parent_data" in st.session_state:
        parent_dashboard()
    else:
        parent_login()


def parent_login():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.session_state.pop('parent_otp_email', None)
            st.rerun()

    st.header('Parent Login', text_alignment='center')
    st.caption("Use the parent email registered with your child's profile. We will email you a one-time code.")
    st.space()

    email = st.text_input("Parent email", placeholder="parent@gmail.com").strip().lower()

    if st.button("Send OTP", type="primary", icon=":material/mail:"):
        if not email or "@" not in email:
            st.warning("Please enter a valid email.")
        else:
            send_failed = False
            children = get_children_for_parent(email)
            if children:
                try:
                    parent_name = children[0].get('parent_name') or "Parent"
                    with st.spinner("Sending OTP..."):
                        send_and_save_otp(email, OTP_PURPOSE, parent_name)
                    st.session_state.parent_otp_email = email
                except ValueError as e:
                    st.warning(str(e))
                    st.session_state.parent_otp_email = email
                except Exception as e:
                    st.error(f"Could not send OTP: {e}")
                    send_failed = True
            else:
                st.session_state.pop('parent_otp_email', None)
            # same message whether or not the email exists (no account enumeration)
            if not send_failed:
                st.info("If this email is linked to a student, a 6-digit OTP has been sent. It is valid for 10 minutes.")

    otp_email = st.session_state.get('parent_otp_email')
    if otp_email and otp_email == email:
        otp = st.text_input("Enter OTP", max_chars=6, placeholder="6-digit OTP")
        if st.button("Verify & Login", type="primary"):
            ok, msg = verify_otp(email, otp, OTP_PURPOSE)
            if ok:
                children = get_children_for_parent(email)
                if not children:
                    st.error("No linked student found for this email.")
                else:
                    st.session_state.parent_data = {
                        'email': email,
                        'name': children[0].get('parent_name') or "Parent",
                    }
                    st.session_state.user_role = 'parent'
                    st.session_state.is_logged_in = True
                    st.session_state.pop('parent_otp_email', None)
                    st.toast("Welcome!", icon="👋")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error(msg)

    footer_dashboard()


def parent_dashboard():
    parent = st.session_state.parent_data

    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"Welcome, {parent['name']}")
        if st.button("Logout", type="secondary", key="loginbackbtn", shortcut="control+backspace"):
            del st.session_state.parent_data
            st.session_state['is_logged_in'] = False
            st.rerun()

    # Re-validated on every run: the parent can only ever see these children
    children = get_children_for_parent(parent['email'])
    if not children:
        st.warning("No students are linked to your email.")
        footer_dashboard()
        return

    options = {
        f"{c['name']} — Roll {c.get('roll_no') or 'N/A'} (Sec {c.get('section') or 'N/A'})": c
        for c in children
    }
    label = st.selectbox("Select child", list(options.keys())) if len(options) > 1 else list(options.keys())[0]
    child = options[label]
    sid = child['student_id']

    st.markdown(f"### 👤 {child['name']}")
    st.caption(f"{child.get('course') or ''} {('Year ' + str(child['year'])) if child.get('year') else ''}".strip())

    t1, t2, t3, t4 = st.tabs(["🏠 Overview", "📋 Attendance", "📝 Marks", "📢 Announcements"])
    with t1:
        render_child_overview(sid, viewer="parent")
        st.divider()
        render_timetable(sid)
    with t2:
        render_attendance_history(sid, viewer="parent")
    with t3:
        render_marks(sid, viewer="parent")
    with t4:
        render_announcements(sid, viewer="parent")

    footer_dashboard()
