from collections import OrderedDict
from datetime import date

import streamlit as st

from src.database.config import supabase
from src.database.db import get_student_subjects
from src.services.leave_service import (
    submit_leave, list_for_student, list_for_teacher, review_leave, get_document_url
)

WHOLE_DAY = "Whole day (all my subjects)"
STATUS_ICON = {"pending": "🟡", "approved": "🟢", "rejected": "🔴"}


def _whole_day(student_id, kind, start, end, reason):
    """One request per enrolled subject, all sharing one group_id. All-or-nothing in the database."""
    subject_ids = [n['subjects']['subject_id'] for n in get_student_subjects(student_id)
                   if n.get('subjects')]
    try:
        res = supabase.rpc("leave_create_whole_day", {
            "p_student_id": str(student_id),
            "p_subject_ids": [str(s) for s in subject_ids],
            "p_start": str(start), "p_end": str(end),
            "p_kind": kind, "p_reason": reason,
        }).execute()
    except Exception as exc:
        msg = str(getattr(exc, "message", "") or exc)
        print(f"leave_create_whole_day failed: {type(exc).__name__}")
        if "overlaps" in msg:
            return False, "You already have a pending or approved leave that overlaps these dates. " \
                          "Choose different dates, or ask your teacher about the existing request."
        if "at most 30 days" in msg:
            return False, "A leave request can cover at most 30 days."
        if "reason" in msg:
            return False, "Please give a reason of 5 to 500 characters."
        return False, "Could not submit the whole-day leave. Please try again."
    return True, f"Submitted for {len(subject_ids)} subject(s). Each teacher will review their subject."


def _leave_form(student_id, subs):
    options = {f"{s['name']} - {s['subject_code']}": s['subject_id'] for s in subs}
    with st.container(border=True):
        kind = st.radio("Type", ["leave", "medical"], horizontal=True, key="leave_kind")
        scope = st.radio("Covers", [WHOLE_DAY, "One subject only"], horizontal=True, key="leave_scope")
        label = None
        if scope != WHOLE_DAY:
            label = st.selectbox("Subject", list(options.keys()), key="leave_sub")
        c1, c2 = st.columns(2)
        start = c1.date_input("From", value=date.today(), key="leave_from")
        end = c2.date_input("To", value=date.today(), key="leave_to")
        reason = st.text_area("Reason", max_chars=500, key="leave_reason")
        doc = None
        if scope != WHOLE_DAY:
            doc = st.file_uploader("Medical certificate (optional, PDF/JPG/PNG, max 2 MB)",
                                   type=["pdf", "jpg", "jpeg", "png"], key="leave_doc")
        else:
            st.caption("A whole-day request covers every subject you are enrolled in. "
                       "A certificate can be attached to a single-subject request.")
        if st.button("Submit request", type="primary", key="leave_submit"):
            if scope == WHOLE_DAY:
                ok, msg = _whole_day(student_id, kind, start, end, reason)
            else:
                ok, msg = submit_leave(
                    student_id, options[label], kind, start, end, reason,
                    doc_name=doc.name if doc else None,
                    doc_bytes=doc.getvalue() if doc else None,
                )
            (st.success if ok else st.error)(msg)


def _my_requests(student_id):
    st.subheader("My requests")
    rows = list_for_student(student_id)
    if not rows:
        st.caption("No leave requests yet.")
        return
    groups = OrderedDict()
    for r in rows:
        key = r.get('group_id') or f"single-{r['id']}"
        groups.setdefault(key, []).append(r)
    for key, items in groups.items():
        first = items[0]
        if first.get('group_id'):
            st.markdown(f"**Whole-day {first['kind']}** · {first['start_date']} → {first['end_date']}")
            for r in items:
                sub = r.get('subjects') or {}
                st.write(f"{STATUS_ICON.get(r['status'], '')} {sub.get('name', '?')} · {r['status']}")
                if r.get('review_note'):
                    st.caption(f"Teacher note: {r['review_note']}")
        else:
            sub = first.get('subjects') or {}
            st.write(f"{STATUS_ICON.get(first['status'], '')} **{sub.get('name', '?')}** · {first['kind']} · "
                     f"{first['start_date']} → {first['end_date']} · {first['status']}")
            if first.get('review_note'):
                st.caption(f"Teacher note: {first['review_note']}")


def student_leave_tab(student_id):
    st.header("📝 Leave / Medical Requests")
    subs = [n['subjects'] for n in get_student_subjects(student_id) if n.get('subjects')]
    if not subs:
        st.info("Enroll in a subject first.")
        return
    _leave_form(student_id, subs)
    _my_requests(student_id)


def teacher_leave_tab(teacher_id):
    st.subheader("Pending leave requests")
    pending = list_for_teacher(teacher_id, 'pending')
    if not pending:
        st.info("No pending requests.")
        return
    for r in pending:
        stu, sub = r.get('students') or {}, r.get('subjects') or {}
        with st.container(border=True):
            tag = " · whole-day request" if r.get('group_id') else ""
            st.write(f"**{stu.get('name', '?')}** ({stu.get('roll_no', 'N/A')}) · "
                     f"{sub.get('name', '?')} · {r['kind']}{tag}")
            st.caption(f"{r['start_date']} → {r['end_date']}")
            st.write(r['reason'])
            if r.get('document_path'):
                if st.button("📎 Open certificate", key=f"doc_{r['id']}"):
                    url = get_document_url(r['id'], teacher_id)
                    st.markdown(f"[Open (link valid 5 min)]({url})") if url else st.error("Not available.")
            note = st.text_input("Note (optional)", key=f"note_{r['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Approve", key=f"ap_{r['id']}", type="primary"):
                ok, msg = review_leave(r['id'], teacher_id, True, note)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if c2.button("Reject", key=f"rj_{r['id']}", type="secondary"):
                ok, msg = review_leave(r['id'], teacher_id, False, note)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
