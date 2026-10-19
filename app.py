import httpx
import streamlit as st

from src.screens.home_screen import home_screen
from src.screens.teacher_screen import teacher_screen
from src.screens.student_screen import student_screen
from src.screens.parent_screen import parent_screen
from src.screens.admin_screen import admin_screen
from src.components.dialog_auto_enroll import auto_enroll_dialog
from src.services.scheduler import check_and_send_weekly_reports
from src.pipelines.self_learning import auto_retrain_if_needed


def main():
    st.set_page_config(
        page_title='SnapClass - Making Attendance faster using AI',
        page_icon="https://i.ibb.co/YTYGn5qV/logo.png"
    )

    # Monday weekly parent reports (background, once per process)
    check_and_send_weekly_reports()

    # Auto retrain model once per session if needed
    if 'model_checked' not in st.session_state:
        retrained, msg = auto_retrain_if_needed()
        if retrained:
            print(f"Auto retrain: {msg}")
        st.session_state['model_checked'] = True

    if 'login_type' not in st.session_state:
        st.session_state['login_type'] = None

    # A scanned attendance QR (?qr-code=XXXXXX) opens the student portal
    if st.query_params.get('qr-code') and st.session_state['login_type'] != 'student':
        st.session_state['login_type'] = 'student'

    # Admin link on the home page: /?admin=1
    if st.query_params.get('admin') and st.session_state['login_type'] is None:
        st.session_state['login_type'] = 'admin'

    match st.session_state['login_type']:
        case 'teacher':
            teacher_screen()
        case 'student':
            student_screen()
        case 'parent':
            parent_screen()
        case 'admin':
            admin_screen()
        case None:
            home_screen()

    join_code = st.query_params.get('join-code')
    if join_code:
        if st.session_state.login_type != 'student':
            st.session_state.login_type = 'student'
            st.rerun()
        if st.session_state.get('is_logged_in') and st.session_state.get('user_role') == 'student':
            auto_enroll_dialog(join_code)


try:
    main()
except httpx.TransportError as e:
    print(f"Network error: {e!r}")
    st.error("⚠️ Can't reach the database right now (network problem). "
             "Check your internet connection, then retry.")
    if st.button("Retry"):
        st.rerun()
