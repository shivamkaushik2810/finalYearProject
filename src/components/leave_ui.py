from datetime import date
import streamlit as st

from src.database.db import get_student_subjects
from src.services.leave_service import (
    submit_leave, list_for_student, list_for_teacher, review_leave, get_document_url
)


def student_leave_tab(student_id):
    st.header("📝 Leave / Medical Requests")
    subs = [n['subjects'] for n in get_student_subjects(student_id) if n.get('subjects')]
    if not subs:
        st.info("Enroll in a subject first.")
        return

    options = {f"{s['name']} - {s['subject_code']}": s['subject_id'] for s in subs}
    with st.container(border=True):
        label = st.selectbox("Subject", list(options.keys()), key="leave_sub")
        kind = st.radio("Type", ["leave", "medical"], horizontal=True, key="leave_kind")
        c1, c2 = st.columns(2)
        start = c1.date_input("From", value=date.today(), key="leave_from")
        end = c2.date_input("To", value=date.today(), key="leave_to")
        reason = st.text_area("Reason", max_chars=500, key="leave_reason")
        doc = st.file_uploader("Medical certificate (optional, PDF/JPG/PNG, max 2 MB)",
                               type=["pdf", "jpg", "jpeg", "png"], key="leave_doc")
        if st.button("Submit request", type="primary", key="leave_submit"):
            ok, msg = submit_leave(
                student_id, options[label], kind, start, end, reason,
                doc_name=doc.name if doc else None,
                doc_bytes=doc.getvalue() if doc else None,
            )
            (st.success if ok else st.error)(msg)

    st.subheader("My requests")
    for r in list_for_student(student_id):
        icon = {"pending": "🟡", "approved": "🟢", "rejected": "🔴"}[r['status']]
        sub = r.get('subjects') or {}
        st.write(f"{icon} **{sub.get('name', '?')}** · {r['kind']} · "
                 f"{r['start_date']} → {r['end_date']} · {r['status']}")
        if r.get('review_note'):
            st.caption(f"Teacher note: {r['review_note']}")


def teacher_leave_tab(teacher_id):
    st.subheader("Pending leave requests")
    pending = list_for_teacher(teacher_id, 'pending')
    if not pending:
        st.info("No pending requests.")
        return
    for r in pending:
        stu, sub = r.get('students') or {}, r.get('subjects') or {}
        with st.container(border=True):
            st.write(f"**{stu.get('name', '?')}** ({stu.get('roll_no', 'N/A')}) · "
                     f"{sub.get('name', '?')} · {r['kind']}")
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
