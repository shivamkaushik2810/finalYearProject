import math
from datetime import datetime
import pandas as pd
import streamlit as st
from src.database.config import supabase
from src.database.attendance_status import eligible
from src.database.db import get_marks_by_student
from src.pipelines.grading import grade_for
from src.services.report_export import df_pdf

REQUIRED_PCT = 75


def _fmt_ts(ts):
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00')).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return str(ts or "Unknown")


def _icon(pct):
    return "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"


def _load_logs(student_id):
    res = supabase.table('attendance_logs')\
        .select('student_id, subject_id, is_present, timestamp, status, subjects(name, subject_code)')\
        .eq('student_id', student_id)\
        .order('timestamp', desc=True)\
        .execute()
    return eligible(res.data)


def _subject_stats(logs):
    stats = {}
    for l in logs:
        sid = l.get('subject_id')
        if sid is None:
            continue
        sub = l.get('subjects') or {}
        s = stats.setdefault(sid, {
            'name': sub.get('name', 'Unknown'),
            'code': sub.get('subject_code', ''),
            'total': 0, 'present': 0
        })
        s['total'] += 1
        if l.get('is_present'):
            s['present'] += 1
    return stats


def _classes_needed(present, total, target=REQUIRED_PCT):
    """Smallest x such that (present + x) / (total + x) >= target%"""
    t = target / 100
    need = (t * total - present) / (1 - t)
    return max(0, math.ceil(need - 1e-9))


def render_child_overview(student_id, viewer="student"):
    logs = _load_logs(student_id)
    if not logs:
        st.info("No attendance recorded yet.")
        return

    stats = _subject_stats(logs)
    total = sum(s['total'] for s in stats.values())
    present = sum(s['present'] for s in stats.values())
    pct = round(present / total * 100, 1) if total else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Classes", total)
    c2.metric("✅ Present", present)
    c3.metric("❌ Absent", total - present)
    c4.metric("Overall", f"{_icon(pct)} {pct}%")

    if pct < REQUIRED_PCT:
        need = _classes_needed(present, total)
        st.warning(f"⚠️ Overall attendance is below {REQUIRED_PCT}%. "
                   f"{need} consecutive present class(es) are needed to reach {REQUIRED_PCT}%.")
    else:
        st.success(f"Attendance is above the {REQUIRED_PCT}% requirement.")

    st.subheader("Subject-wise attendance")
    for s in sorted(stats.values(), key=lambda x: x['name']):
        sp = round(s['present'] / s['total'] * 100, 1) if s['total'] else 0
        with st.container(border=True):
            a, b = st.columns([3, 2])
            a.write(f"**{s['name']}** ({s['code']})")
            b.write(f"{_icon(sp)} {s['present']}/{s['total']} — {sp}%")
            st.progress(min(max(sp / 100, 0.0), 1.0))
            if sp < REQUIRED_PCT:
                st.caption(f"Needs {_classes_needed(s['present'], s['total'])} more present class(es) to reach {REQUIRED_PCT}%.")


def render_attendance_history(student_id, viewer="student"):
    logs = _load_logs(student_id)
    if not logs:
        st.info("No attendance records found yet.")
        return

    rows = [{
        "Date & Time": _fmt_ts(l.get('timestamp')),
        "Subject": (l.get('subjects') or {}).get('name', 'Unknown'),
        "Status": "✅ Present" if l.get('is_present') else "❌ Absent",
    } for l in logs]
    df = pd.DataFrame(rows)

    subjects = ["All"] + sorted(df["Subject"].unique().tolist())
    choice = st.selectbox("Filter by subject", subjects, key=f"hist_{viewer}_{student_id}")
    if choice != "All":
        df = df[df["Subject"] == choice]
    st.dataframe(df, hide_index=True, width='stretch')
    st.download_button("⬇️ Download attendance report (PDF)",
                       df_pdf(df, f"Attendance Report - {_student_name(student_id)}", f"Subject: {choice}"),
                       file_name=f"attendance_{student_id}.pdf", mime="application/pdf",
                       key=f"pdf_hist_{viewer}_{student_id}")


def render_marks(student_id, viewer="student"):
    marks = get_marks_by_student(student_id)
    if not marks:
        st.info("No marks have been uploaded yet.")
        return

    rows = []
    for m in marks:
        sub = m.get('subjects') or {}
        mx = m.get('max_marks') or 0
        got = m.get('marks_obtained') or 0
        p = round(got / mx * 100, 1) if mx else 0
        rows.append({
            "Subject": sub.get('name', 'Unknown'),
            "Exam": m.get('exam_type', ''),
            "Marks": f"{got}/{mx}",
            "Percent": f"{_icon(p)} {p}%",
            "Grade": grade_for(p),
            "Remarks": m.get('remarks') or "",
        })

    tot_got = sum((m.get('marks_obtained') or 0) for m in marks)
    tot_max = sum((m.get('max_marks') or 0) for m in marks)
    overall = round(tot_got / tot_max * 100, 1) if tot_max else 0
    st.metric("Overall marks", f"{_icon(overall)} {overall}% (Grade {grade_for(overall)})", f"{tot_got}/{tot_max}")
    _mdf = pd.DataFrame(rows)
    st.dataframe(_mdf, hide_index=True, width='stretch')
    st.download_button("⬇️ Download marks report (PDF)",
                       df_pdf(_mdf, f"Marks Report - {_student_name(student_id)}", f"Overall: {overall}% (Grade {grade_for(overall)})"),
                       file_name=f"marks_{student_id}.pdf", mime="application/pdf",
                       key=f"pdf_marks_{viewer}_{student_id}")


def render_announcements(student_id, viewer="student"):
    """Announcements for the student's subjects (or general ones). Tolerant of column names."""
    st.subheader("📢 Announcements")
    try:
        sub_res = supabase.table('subject_students').select('subject_id').eq('student_id', student_id).execute()
        my_subjects = {r['subject_id'] for r in (sub_res.data or [])}

        try:
            res = supabase.table('announcements').select('*').order('created_at', desc=True).limit(30).execute()
        except Exception:
            res = supabase.table('announcements').select('*').limit(30).execute()
        rows = res.data or []
    except Exception as e:
        st.info("Announcements are not available right now.")
        print(f"Announcements error: {e}")
        return

    shown = 0
    for r in rows:
        sid = r.get('subject_id')
        if sid and sid not in my_subjects:
            continue
        title = r.get('title') or r.get('subject') or "Announcement"
        body = r.get('message') or r.get('content') or r.get('body') or r.get('description') or ""
        with st.container(border=True):
            st.write(f"**{title}**")
            if body:
                st.write(body)
            if r.get('created_at'):
                st.caption(_fmt_ts(r['created_at']))
        shown += 1
        if shown >= 10:
            break

    if shown == 0:
        st.info("No announcements yet.")


def _student_name(student_id):
    try:
        res = supabase.table('students').select('name').eq('student_id', student_id).execute()
        return (res.data or [{}])[0].get('name', '')
    except Exception:
        return ''
