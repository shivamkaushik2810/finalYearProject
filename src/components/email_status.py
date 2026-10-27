import streamlit as st
from src.services.email_queue import get_job


def _summarize(job):
    parts, problem = [], False
    if job["sent"]:
        parts.append(f"📧 {job['sent']} student email(s) sent for {job['subject_name']}.")
    ts = job["teacher_status"]
    if ts == "sent":
        parts.append("📊 Summary email sent to teacher.")
    elif ts == "no_email":
        parts.append("ℹ️ No teacher email on file, so no summary was sent.")
    elif ts == "failed":
        parts.append("⚠️ The teacher summary email failed to send.")
        problem = True
    if job["no_email"]:
        names = ", ".join(job["no_email"][:5]) + ("…" if len(job["no_email"]) > 5 else "")
        parts.append(f"⚠️ {len(job['no_email'])} present student(s) have no email on file: {names}")
        problem = True
    if job["failed"]:
        name, reason = job["failed"][0]
        parts.append(f"⚠️ {len(job['failed'])} email(s) failed to send (e.g. {name}: {reason}).")
        problem = True
    if job["deferred"]:
        reason = job["block_reason"] or "unknown"
        if reason == "daily_limit":
            reason = "daily sending limit reached"
        parts.append(f"⚠️ {job['deferred']} email(s) were NOT sent ({reason}). "
                     "Attendance itself is saved.")
        problem = True
    return ("warning" if problem else "success"), "\n\n".join(parts) or "No emails to send."


@st.fragment(run_every=3)
def email_status_fragment():
    notices = st.session_state.setdefault("email_notices", [])
    pending = []
    for jid in list(st.session_state.get("email_job_ids", [])):
        job = get_job(jid)
        if job is None:
            continue
        if job["status"] in ("queued", "running"):
            pending.append(jid)
            st.caption(f"📧 Sending emails for {job['subject_name']}… ({job['sent']} sent so far)")
        elif job["status"] == "error":
            notices.append(("warning", "⚠️ Email sending crashed unexpectedly. Attendance is saved."))
        else:
            notices.append(_summarize(job))
    st.session_state["email_job_ids"] = pending
    for level, msg in notices:
        getattr(st, level)(msg)
    if notices and st.button("Dismiss email notices", key="dismiss_email_notices"):
        st.session_state["email_notices"] = []
        st.rerun(scope="fragment")
