import streamlit as st
from src.components.section_analytics import show_section_analytics
from src.components.teacher_session_history import show_teacher_session_history
from src.components.defaulter_emails import show_defaulter_email_panel


def show_admin_analytics_hub():
    t1, t2, t3 = st.tabs([
        "📊 Section Analytics",
        "🧑‍🏫 Teacher Sessions",
        "🚨 Defaulters & Parent Emails",
    ])
    with t1:
        show_section_analytics()
    with t2:
        show_teacher_session_history()
    with t3:
        show_defaulter_email_panel(teacher_id=None, key="admin_def")
