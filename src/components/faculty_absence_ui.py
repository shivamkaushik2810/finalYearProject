"""Admin: faculty absences. Approve or reject requests, record emergency or unplanned absences,
and cancel approved ones. Every write goes through faculty_absence_service, which re-checks the
admin session on the server."""
import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.services import faculty_absence_service as svc
from src.services.faculty_absence_rules import KINDS
from src.services.timetable_service import require_admin

STATUS_OPTIONS = ["pending", "approved", "rejected", "cancelled", "completed", "all"]


def _approved_teachers():
    rows = (supabase.table("teachers").select("teacher_id,name,username")
            .eq("status", "approved").order("name").execute().data or [])
    return {f"{r['name']} (@{r['username']})": str(r["teacher_id"]) for r in rows}


def _do(action):
    try:
        action()
    except (svc.AbsenceError, PermissionError) as exc:
        st.error(str(exc))
        return False
    return True


def show_faculty_absences():
    st.subheader("🧑‍🏫 Faculty absences")
    admin_id = (st.session_state.get("admin_data") or {}).get("id")
    try:
        require_admin(admin_id)
    except PermissionError as exc:
        st.error(str(exc))
        return

    teachers = _approved_teachers()
    names = {tid: label.split(" (@")[0] for label, tid in teachers.items()}

    status = st.selectbox("Show", STATUS_OPTIONS, index=0, key="fa_status")
    rows = svc.list_absences(admin_id=admin_id, status=None if status == "all" else status)
    if rows:
        st.dataframe(pd.DataFrame([{
            "ID": r["id"],
            "Teacher": names.get(str(r["teacher_id"]), str(r["teacher_id"])[:8]),
            "From": r["start_date"], "To": r["end_date"], "Kind": r["kind"],
            "Periods": "whole day" if not r["periods"] else ", ".join(str(p) for p in r["periods"]),
            "Status": r["status"], "Reason": r["reason"], "Requested by": r["requested_by"],
        } for r in rows]), hide_index=True, width="stretch")
    else:
        st.info("No absences with this status.")

    st.markdown("**Decide**")
    actionable = [r for r in rows if r["status"] in ("pending", "approved")]
    if not actionable:
        st.caption("Nothing to decide in this view.")
    else:
        labels = {f"#{r['id']} {names.get(str(r['teacher_id']), '?')} "
                  f"{r['start_date']} to {r['end_date']} ({r['status']})": r for r in actionable}
        pick = labels[st.selectbox("Absence", list(labels), key="fa_pick")]
        note = st.text_input("Note (optional)", max_chars=300, key="fa_note")
        c1, c2 = st.columns(2)
        if pick["status"] == "pending":
            if c1.button("Approve", type="primary", key="fa_approve"):
                if _do(lambda: svc.decide_absence(admin_id, pick["id"], "approved", note)):
                    st.rerun()
            if c2.button("Reject", key="fa_reject"):
                if _do(lambda: svc.decide_absence(admin_id, pick["id"], "rejected", note)):
                    st.rerun()
        elif c1.button("Cancel absence", key="fa_cancel"):
            if _do(lambda: svc.decide_absence(admin_id, pick["id"], "cancelled", note)):
                st.rerun()

    st.markdown("**Record an absence**")
    if not teachers:
        st.info("No approved teachers yet. Approve teacher accounts first.")
        return
    with st.form("fa_record"):
        teacher_label = st.selectbox("Teacher", list(teachers), key="fa_teacher")
        kind = st.selectbox("Kind", list(KINDS), key="fa_kind")
        c1, c2 = st.columns(2)
        start = c1.date_input("From", key="fa_from")
        end = c2.date_input("To", key="fa_to")
        periods = st.multiselect("Periods (leave empty for the whole day)", list(range(1, 9)), key="fa_periods")
        reason = st.text_area("Reason", max_chars=500, key="fa_reason")
        submit = st.form_submit_button("Record absence", type="primary")
    if submit:
        if _do(lambda: svc.request_absence("admin", admin_id, teachers[teacher_label], start, end,
                                           kind, periods or None, reason)):
            st.toast("Absence recorded as approved.")
            st.rerun()
