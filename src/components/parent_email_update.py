import streamlit as st
from src.database.config import supabase
from src.services.parent_email_rules import validate_parent_email
from src.services.otp_service import (
    send_and_save_otp, verify_otp, is_email_verified, mark_email_verified
)


def show_parent_email_update(student):
    """Show on the student dashboard when parent_needs_update is True."""
    if not student.get("parent_needs_update"):
        return

    with st.container(border=True):
        st.warning("⚠️ Your parent email is missing or invalid. "
                   "Enter and verify it so weekly reports can be sent.")
        p_name = st.text_input("Parent Name", key="pu_name")
        p_email = st.text_input("Parent Email", key="pu_email")

        ok, msg = validate_parent_email(
            student.get("email"), p_email, student.get("student_id")
        ) if p_email else (False, "")
        if p_email and not ok:
            st.error(msg)

        if ok and not is_email_verified(p_email, "parent_email"):
            if st.button("Send OTP", key="pu_send"):
                try:
                    send_and_save_otp(p_email, "parent_email", p_name or "Parent")
                    st.success("OTP sent to the parent email.")
                except Exception as e:
                    st.error(f"Could not send OTP: {e}")
            otp = st.text_input("Enter OTP", max_chars=6, key="pu_otp")
            if otp and len(otp) == 6 and st.button("Verify OTP", key="pu_verify"):
                valid, message = verify_otp(p_email, otp, "parent_email")
                if valid:
                    mark_email_verified(p_email, "parent_email")
                    st.rerun()
                else:
                    st.error(message)

        if ok and is_email_verified(p_email, "parent_email"):
            if st.button("Save parent details", type="primary", key="pu_save"):
                supabase.table("students").update({
                    "parent_email": p_email.strip().lower(),
                    "parent_name": p_name,
                    "parent_needs_update": False,
                }).eq("student_id", student["student_id"]).execute()
                st.session_state.student_data["parent_email"] = p_email.strip().lower()
                st.session_state.student_data["parent_needs_update"] = False
                st.success("Parent details saved.")
                st.rerun()
