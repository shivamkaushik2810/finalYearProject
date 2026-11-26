"""Teacher: request planned absences, see notices and substitutions assigned to you, and accept
or decline them. Every write goes through a service, and the database re-checks each rule."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.services import faculty_absence_service as svc
from src.services import substitution_manual_service as msvc

IST = ZoneInfo("Asia/Kolkata")


def _today():
    return datetime.now(IST).date()


def _inbox(teacher_id):
    from src.services import notification_service as nsvc
    try:
        items = nsvc.my_inbox(teacher_id, limit=10)
    except Exception as exc:
        print(f"inbox failed: {type(exc).__name__}")
        return
    unread = [i for i in items if not i.get("read_at")]
    if not unread:
        return
    with st.expander(f"Notices ({len(unread)} unread)", expanded=True):
        for i in unread:
            st.write(f"**{i['subject']}**")
            st.caption(i["body"])
            if st.button("Mark as read", key=f"inbox_read_{i['id']}"):
                nsvc.mark_read(teacher_id, i["id"])
                st.rerun()


def show_my_substitutions(teacher_id):
    _inbox(teacher_id)
    st.markdown("**Substitutions assigned to me (next 14 days)**")
    try:
        rows = msvc.my_substitutions(teacher_id, start=_today(), days=14)
    except msvc.ManualError as exc:
        st.error(str(exc))
        return
    if not rows:
        st.info("No substitutions are assigned to you in the next 14 days.")
        return
    for r in rows:
        with st.container(border=True):
            st.write(f"**{r['substitution_date']}, P{r['period_no']}**: {r['subject_code']} "
                     f"for {r['original_teacher_code']}, section {r['section_code']}, "
                     f"room {r.get('room') or 'to be confirmed'}")
            if r.get("accepted_at"):
                st.caption("You accepted this class.")
            elif st.button("Accept", key=f"sub_acc_{r['id']}"):
                try:
                    msvc.accept_substitution(teacher_id, r["id"])
                except msvc.ManualError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
            with st.expander("Decline this class"):
                reason = st.text_input("Reason (required)", max_chars=300, key=f"sub_reason_{r['id']}")
                if st.button("Decline", key=f"sub_dec_{r['id']}"):
                    try:
                        msvc.decline_substitution(teacher_id, r["id"], reason)
                    except msvc.ManualError as exc:
                        st.error(str(exc))
                    else:
                        st.toast("Declined. The class is now unassigned, and the administrator can re-plan it.")
                        st.rerun()


def show_my_absences(teacher_id):
    st.subheader("My absences")
    st.caption("Request a planned absence. An administrator approves it before it takes effect. "
               "Emergency and unplanned absences are recorded by the administrator.")

    with st.form("teacher_absence_request", clear_on_submit=True):
        c1, c2 = st.columns(2)
        start = c1.date_input("From", value=_today(), min_value=_today(), key="tab_from")
        end = c2.date_input("To", value=_today(), min_value=_today(), key="tab_to")
        periods = st.multiselect("Periods (leave empty for the whole day)",
                                 list(range(1, 9)), key="tab_periods")
        reason = st.text_area("Reason", max_chars=500, key="tab_reason",
                              placeholder="For example: medical appointment, conference")
        submit = st.form_submit_button("Send request", type="primary")

    if submit:
        try:
            svc.request_absence("teacher", teacher_id, teacher_id, start, end,
                                "planned", periods or None, reason)
        except (svc.AbsenceError, PermissionError) as exc:
            st.error(str(exc))
        else:
            st.success("Request sent. It is pending until an administrator approves it.")

    st.markdown("**My requests**")
    rows = svc.list_absences(teacher_id=teacher_id)
    if not rows:
        st.info("You have no absence requests.")
    else:
        st.dataframe(pd.DataFrame([{
            "From": r["start_date"],
            "To": r["end_date"],
            "Periods": "whole day" if not r["periods"] else ", ".join(str(p) for p in r["periods"]),
            "Status": r["status"],
            "Reason": r["reason"],
            "Decision note": r.get("decision_note") or "",
        } for r in rows]), hide_index=True, width="stretch")

    st.divider()
    show_my_substitutions(teacher_id)
