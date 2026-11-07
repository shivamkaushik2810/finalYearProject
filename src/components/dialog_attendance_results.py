import logging
import time

import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.database.db import create_attendance
from src.services.email_service import send_all_attendance_emails
from src.ui.widgets import stat_cards

log = logging.getLogger(__name__)

LOW_CONFIDENCE = 0.6  # match score below this is flagged for a human check


def _reset_state(on_finish=None):
    st.session_state.voice_attendance_results = None
    st.session_state.attendance_images = []
    if on_finish:
        on_finish()


def show_attendance_result(df, logs, key_prefix="rev", allowed_subject_ids=None, on_finish=None):
    """Review table with a Present checkbox per student. Teachers can fix mistakes before saving.

    df needs the columns Name and ID. An optional Match column (0 to 1) enables low-confidence flags.
    """
    if not logs:
        st.info("There is nothing to review yet.")
        return

    stamp = str(logs[0].get("timestamp", ""))
    subject_id = logs[0].get("subject_id")
    auto_present = {l["student_id"]: bool(l.get("is_present")) for l in logs}
    has_match = "Match" in df.columns

    match_pct = [None if (not has_match or pd.isna(m)) else round(float(m) * 100) for m in
                 (df["Match"] if has_match else [None] * len(df))]
    flag = ["Low confidence: check" if (auto_present.get(i) and m is not None and m < LOW_CONFIDENCE * 100) else ""
            for i, m in zip(df["ID"], match_pct)]
    table = pd.DataFrame({
        "ID": list(df["ID"]),
        "Student": list(df["Name"]),
        "Match": match_pct,
        "Present": [auto_present.get(i, False) for i in df["ID"]],
        "Check": flag,
    })

    summary = st.container()
    st.write("Review attendance, change anything that looks wrong, then confirm.")
    edited = st.data_editor(
        table, hide_index=True, width="stretch", key=f"{key_prefix}_editor_{stamp}",
        disabled=["ID", "Student", "Match", "Check"],
        column_config={
            "ID": None,
            "Present": st.column_config.CheckboxColumn("Present"),
            "Match": st.column_config.NumberColumn("Match", format="%d%%"),
        },
    )

    present_now = int(edited["Present"].sum())
    changed = sum(1 for i, p in zip(edited["ID"], edited["Present"]) if bool(p) != auto_present.get(i, False))
    with summary:
        stat_cards([
            ("Present", present_now, "good"),
            ("Absent", len(edited) - present_now, "bad" if len(edited) - present_now else ""),
            ("Low confidence", sum(1 for f in flag if f), "avg" if any(flag) else ""),
            ("Edited by you", changed, ""),
        ])

    discard_key = f"{key_prefix}_confirm_discard"
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Discard", width="stretch", key=f"danger_{key_prefix}_discard"):
            st.session_state[discard_key] = True
    with col2:
        save_clicked = st.button("Confirm and save", width="stretch", type="primary", key=f"{key_prefix}_save")

    if st.session_state.get(discard_key):
        st.warning("Discard this attendance? The photos and results will be removed.")
        d1, d2 = st.columns(2)
        with d1:
            if st.button("Keep reviewing", key=f"{key_prefix}_keep", width="stretch"):
                st.session_state[discard_key] = False
                st.rerun()
        with d2:
            if st.button("Yes, discard", key=f"danger_{key_prefix}_discard_yes", type="primary", width="stretch"):
                st.session_state[discard_key] = False
                _reset_state(on_finish)
                st.rerun()

    if not save_clicked:
        return

    if allowed_subject_ids is not None and subject_id not in allowed_subject_ids:
        st.error("You can only save attendance for your own subjects.")
        return
    saved_key = f"_saved_{subject_id}_{stamp}"
    if st.session_state.get(saved_key):
        st.info("This attendance was already saved.")
        return

    new_state = {i: bool(p) for i, p in zip(edited["ID"], edited["Present"])}
    final_logs = [dict(l, is_present=new_state.get(l["student_id"], bool(l.get("is_present")))) for l in logs]
    try:
        create_attendance(final_logs)
    except Exception:
        log.exception("Saving attendance failed for subject_id=%s", subject_id)
        st.error("Attendance wasn't saved. Check your connection and try again.")
        return

    st.session_state[saved_key] = True
    st.toast("Attendance saved")
    _send_emails(final_logs)
    _reset_state(on_finish)
    time.sleep(1)
    st.rerun()


def _send_emails(logs):
    try:
        if not logs:
            return
        subject_id = logs[0]["subject_id"]
        timestamp = logs[0]["timestamp"]

        sub_res = supabase.table("subjects").select("name, subject_code, teacher_id") \
            .eq("subject_id", subject_id).execute()
        if not sub_res.data:
            return

        teacher_data = st.session_state.get("teacher_data", {})
        teacher_name = teacher_data.get("name", "Teacher")
        teacher_email = teacher_data.get("email", "")

        enrolled_res = supabase.table("subject_students") \
            .select("student_id, students(student_id, name, email)") \
            .eq("subject_id", subject_id).execute()
        all_enrolled = [n["students"] for n in (enrolled_res.data or []) if n.get("students")]
        if not all_enrolled:
            st.warning("No enrolled students were found, so no emails were sent.")
            return

        with st.spinner("Sending emails to students and teacher..."):
            ok, fail, teacher_ok = send_all_attendance_emails(
                logs=logs,
                subject_name=sub_res.data[0]["name"],
                subject_code=sub_res.data[0]["subject_code"],
                teacher_name=teacher_name,
                teacher_email=teacher_email,
                timestamp=timestamp,
                all_enrolled_students=all_enrolled,
            )

        if ok > 0:
            st.toast(f"Emails sent to {ok} student(s)")
        if fail > 0:
            st.warning(f"{fail} student email(s) were not sent. The student may have no email on file, "
                       "or sending failed.")
        if teacher_ok:
            st.toast("Summary email sent to teacher")
        elif not teacher_email:
            st.info("No teacher email on file, so no summary was sent.")
    except Exception:
        log.exception("Post-save email step failed")
        st.warning("Attendance is saved, but the emails couldn't be sent.")


@st.dialog("Attendance Reports")
def attendance_result_dialog(df, logs):
    show_attendance_result(df, logs)
