import streamlit as st


def require_admin():
    """Every analytics data function calls this first."""
    admin = st.session_state.get("admin_data")
    if not admin or not admin.get("id"):
        raise PermissionError("Administrator access required.")
    return admin
