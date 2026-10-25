import html
from collections import defaultdict

import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.services.email_service import _send

try:
    from src.database.db import get_marks_by_student
except Exception:  # marks are optional in the email
    get_marks_by_student = None


def _bar(pct):
    color = "#28a745" if pct >= 75 else "#e74c3c" if pct < 50 else "#f39c12"
    return (
        f"<div style='background:#eee;border-radius:6px;width:140px;height:10px;'>"
        f"<div style='background:{color};width:{min(max(pct, 0), 100)}%;"
        f"height:10px;border-radius:6px;'></div></div>"
    )


def _load_subjects(subjects):
    if subjects and all(isinstance(s, dict) and "subject_id" in s for s in subjects):
        return {s["subject_id"]: s for s in subjects}
    res = supabase.table("subjects").select("subject_id, name, subject_code").execute()
    return {s["subject_id"]: s for s in (res.data or [])}


def _compute(subject_map):
    """Return {student_id: {"student": {...}, "subjects": {sid: [present, total]}}}."""
    ids = list(subject_map.keys())
    if not ids:
        return {}
    enr = (
        supabase.table("subject_students")
        .select("student_id, subject_id, students(student_id, name, roll_no, section, parent_email, parent_name)")
        .in_("subject_id", ids)
        .execute()
    )
    logs = (
        supabase.table("attendance_logs")
        .select("student_id, subject_id, is_present")
        .in_("subject_id", ids)
        .execute()
    )
    data = {}
    for n in enr.data or []:
        stu = n.get("students")
        if stu:
            data.setdefault(stu["student_id"], {"student": stu, "subjects": defaultdict(lambda: [0, 0])})
    for log in logs.data or []:
        rec = data.get(log.get("student_id"))
        if rec is None:
            continue
        cell = rec["subjects"][log["subject_id"]]
        cell[1] += 1
        if log.get("is_present"):
            cell[0] += 1
    return data


def _build_email(student, subj_rows, overall_pct, marks):
    name = html.escape(str(student.get("name") or "Student"))
    parent = html.escape(str(student.get("parent_name") or "Parent"))
    att_rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>{html.escape(str(r['name']))}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center'>{r['present']}/{r['total']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{r['pct']}% {_bar(r['pct'])}</td></tr>"
        for r in subj_rows
    )
    marks_html = ""
    if marks:
        mrows = "".join(
            f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>"
            f"{html.escape(str((m.get('subjects') or {}).get('name', '')))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee'>{html.escape(str(m.get('exam_type', '')))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center'>"
            f"{m.get('marks_obtained')}/{m.get('max_marks')}</td></tr>"
            for m in marks
        )
        marks_html = (
            "<h3 style='color:#1A5276'>Marks</h3>"
            "<table width='100%' cellspacing='0' style='font-size:13px'>"
            "<tr style='background:#f8f9fa'><th align='left' style='padding:8px'>Subject</th>"
            "<th align='left' style='padding:8px'>Exam</th><th style='padding:8px'>Marks</th></tr>"
            f"{mrows}</table>"
        )
    body = (
        f"<div style='font-family:Arial,sans-serif;max-width:640px;margin:auto'>"
        f"<h2 style='color:#1A5276'>SnapClass - Attendance Alert</h2>"
        f"<p>Dear <b>{parent}</b>,</p>"
        f"<p>Attendance of <b>{name}</b> is <b style='color:#e74c3c'>{overall_pct}%</b>, "
        f"which is below the required level.</p>"
        f"<h3 style='color:#1A5276'>Attendance</h3>"
        f"<table width='100%' cellspacing='0' style='font-size:13px'>"
        f"<tr style='background:#f8f9fa'><th align='left' style='padding:8px'>Subject</th>"
        f"<th style='padding:8px'>Classes</th><th align='left' style='padding:8px'>Percentage</th></tr>"
        f"{att_rows}</table>{marks_html}"
        f"<p style='color:#999;font-size:12px'>Automated message from SnapClass.</p></div>"
    )
    plain = f"Dear {student.get('parent_name') or 'Parent'}, attendance of {student.get('name')} is {overall_pct}%, below the required level."
    return body, plain


def defaulter_email_panel(subjects=None, threshold=75, *args, **kwargs):
    st.subheader("Defaulters - Parent Email")

    # Only logged-in users may use this panel
    if not st.session_state.get("is_logged_in"):
        st.error("Please log in to use this feature.")
        return

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 75.0
    threshold = st.slider("Attendance threshold (%)", 10, 100, int(threshold), key="def_email_thr")

    try:
        subject_map = _load_subjects(subjects)
        data = _compute(subject_map)
    except Exception as e:
        st.error(f"Could not load defaulters: {e}")
        return

    rows = []
    for sid, rec in data.items():
        present = sum(v[0] for v in rec["subjects"].values())
        total = sum(v[1] for v in rec["subjects"].values())
        if total == 0:
            continue
        pct = round(present / total * 100, 1)
        if pct < threshold:
            stu = rec["student"]
            rows.append({
                "Send": False, "ID": sid, "Name": stu.get("name"),
                "Roll No": stu.get("roll_no"), "Section": stu.get("section"),
                "Attendance %": pct, "Parent Email": stu.get("parent_email") or "",
            })

    if not rows:
        st.success("No defaulters below this threshold.")
        return

    df = pd.DataFrame(rows).sort_values("Attendance %").reset_index(drop=True)
    edited = st.data_editor(
        df, hide_index=True, width="stretch", key="def_email_table",
        disabled=[c for c in df.columns if c != "Send"],
    )

    chosen = edited[edited["Send"] == True]  # noqa: E712
    if st.button(f"Send email to {len(chosen)} parent(s)", type="primary", disabled=chosen.empty):
        sent_key = "def_email_sent"
        already = st.session_state.setdefault(sent_key, set())
        ok = fail = skipped = 0
        for _, row in chosen.iterrows():
            sid = row["ID"]
            email = (row["Parent Email"] or "").strip()
            if not email or "@" not in email:
                skipped += 1
                continue
            if (sid, str(pd.Timestamp.now().date())) in already:
                skipped += 1
                continue
            try:
                rec = data[sid]
                subj_rows = []
                for sub_id, (p, t) in rec["subjects"].items():
                    if t:
                        subj_rows.append({
                            "name": subject_map.get(sub_id, {}).get("name", "Subject"),
                            "present": p, "total": t, "pct": round(p / t * 100, 1),
                        })
                marks = []
                if get_marks_by_student:
                    try:
                        marks = get_marks_by_student(sid) or []
                    except Exception:
                        marks = []
                body, plain = _build_email(rec["student"], subj_rows, row["Attendance %"], marks)
                _send(email, f"Attendance Alert - {rec['student'].get('name')}", body, plain)
                already.add((sid, str(pd.Timestamp.now().date())))
                ok += 1
            except Exception as e:
                fail += 1
                print(f"Defaulter email failed for {sid}: {e}")
        st.success(f"Sent: {ok} | Failed: {fail} | Skipped (no email / already sent today): {skipped}")
