from datetime import datetime

import pandas as pd
import streamlit as st

from src.database.config import supabase

STATUS = ["present", "absent", "excused"]
PRIOR = ("present", "absent", "excused")


def _fmt(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return str(ts)


def _owns(teacher_id, subject_id):
    r = supabase.table("subjects").select("subject_id").eq("subject_id", subject_id).eq("teacher_id", teacher_id).execute()
    return bool(r.data)


def teacher_attendance_corrections(teacher_id):
    st.subheader("✏️ Correct attendance or cancel a class")
    st.caption("Mark an absence as excused, fix a wrong mark, or cancel a class recorded by mistake. "
               "Excused absences and cancelled classes are left out of attendance percentages.")
    try:
        subs = supabase.table("subjects").select("subject_id, name, subject_code").eq("teacher_id", teacher_id).execute().data or []
    except Exception as e:
        print(f"Corrections: {type(e).__name__}")
        st.error("Could not load your subjects.")
        return
    if not subs:
        st.info("No subjects yet.")
        return
    opts = {f"{s['name']} ({s['subject_code']})": s for s in subs}
    sid = opts[st.selectbox("Subject", list(opts.keys()), key="ac_subject")]["subject_id"]

    try:
        rows = (supabase.table("attendance_logs")
                .select("student_id, timestamp, status, prior_status, status_note, students(name, roll_no)")
                .eq("subject_id", sid).order("timestamp", desc=True).limit(2000).execute().data or [])
    except Exception as e:
        print(f"Corrections: {type(e).__name__}")
        st.error("Attendance status is not set up yet. Run the attendance status SQL in Supabase.")
        return
    sessions = sorted({r["timestamp"] for r in rows}, reverse=True)[:60]
    if not sessions:
        st.info("No classes recorded for this subject yet.")
        return
    ts = st.selectbox("Class", sessions, format_func=_fmt, key="ac_session")
    ses = [r for r in rows if r["timestamp"] == ts]
    cancelled = all(r.get("status") == "cancelled" for r in ses)

    def _done(msg):
        st.cache_data.clear()
        st.toast(msg)
        st.rerun()

    if cancelled:
        st.warning("This class is marked as cancelled and is left out of every attendance figure.")
        if st.button("Restore this class", key=f"ac_restore_{ts}"):
            if not _owns(teacher_id, sid):
                st.error("You can only change your own subjects.")
                return
            for p in PRIOR:
                (supabase.table("attendance_logs")
                 .update({"status": p, "prior_status": None, "status_note": None})
                 .eq("subject_id", sid).eq("timestamp", ts).eq("status", "cancelled").eq("prior_status", p).execute())
            _done("Class restored.")
        return

    df = pd.DataFrame([{
        "student_id": r["student_id"], "Student": (r.get("students") or {}).get("name", ""),
        "Roll": (r.get("students") or {}).get("roll_no", ""),
        "Status": r.get("status") or "absent", "Note": r.get("status_note") or "",
    } for r in sorted(ses, key=lambda r: ((r.get("students") or {}).get("roll_no") or "", (r.get("students") or {}).get("name") or ""))])
    edited = st.data_editor(
        df, hide_index=True, key=f"ac_editor_{sid}_{ts}", disabled=["Student", "Roll"],
        column_config={"student_id": None,
                       "Status": st.column_config.SelectboxColumn("Status", options=STATUS, required=True),
                       "Note": st.column_config.TextColumn("Note", max_chars=200)})

    if st.button("Save changes", type="primary", key=f"ac_save_{ts}"):
        if not _owns(teacher_id, sid):
            st.error("You can only change your own subjects.")
            return
        changed = 0
        for old, new in zip(df.to_dict("records"), edited.to_dict("records")):
            if (old["Status"], old["Note"]) != (new["Status"], new["Note"]):
                if new["Status"] not in STATUS:
                    continue
                (supabase.table("attendance_logs")
                 .update({"status": new["Status"], "status_note": (new["Note"] or "").strip() or None})
                 .eq("subject_id", sid).eq("timestamp", ts).eq("student_id", new["student_id"]).execute())
                changed += 1
        _done(f"Updated {changed} record(s).")

    st.divider()
    reason = st.text_input("Reason for cancelling (optional)", key=f"ac_reason_{ts}", max_chars=200)
    if st.button("Cancel this class", key=f"ac_cancel_{ts}"):
        if not _owns(teacher_id, sid):
            st.error("You can only change your own subjects.")
            return
        for p in PRIOR:
            (supabase.table("attendance_logs")
             .update({"status": "cancelled", "prior_status": p, "status_note": reason.strip() or None})
             .eq("subject_id", sid).eq("timestamp", ts).eq("status", p).execute())
        _done("Class cancelled.")
