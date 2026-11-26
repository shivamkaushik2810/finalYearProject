from datetime import datetime

import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.database.db import get_teacher_subjects
from src.database.attendance_status import eligible
from src.components.filters import subject_label, filter_rows, cascade_filter, fetch_all
from src.services.thresholds import ATTENDANCE_TARGET


def _enrolled_students(subject_id):
    rows = fetch_all(lambda: supabase.table('subject_students')
                     .select('student_id, students(student_id, name, email, roll_no, section, parent_email, course, year)')
                     .eq('subject_id', subject_id).order('student_id'))
    return [r['students'] for r in rows if r.get('students')]


def _attendance_totals(subject_id):
    logs = fetch_all(lambda: supabase.table('attendance_logs')
                     .select('student_id, is_present, status')
                     .eq('subject_id', subject_id)
                     .order('timestamp').order('student_id'))
    totals = {}
    for row in eligible(logs):
        t = totals.setdefault(row['student_id'], [0, 0])
        t[0] += 1
        t[1] += 1 if row.get('is_present') else 0
    return totals


def student_rows(students, totals, search=""):
    """Rows for the table. A student with no classes shows no percentage (never 0%)."""
    search = (search or "").strip().lower()
    rows = []
    for s in sorted(students, key=lambda x: x.get('roll_no') or ''):
        if search and search not in (s.get('name') or '').lower() \
                and search not in (s.get('roll_no') or '').lower():
            continue
        total, present = totals.get(s['student_id'], [0, 0])
        rows.append({
            "Roll No": s.get('roll_no') or "N/A",
            "Name": s.get('name'),
            "Course": s.get('course') or "-",
            "Year": s.get('year') or "-",
            "Section": s.get('section') or "-",
            "Email": s.get('email') or "No email",
            "Parent Email": s.get('parent_email') or "No parent email",
            "Attendance": f"{present}/{total}",
            "Attendance %": round(present / total * 100, 1) if total else None,
        })
    return rows


def teacher_tab_enrolled_students():
    teacher_id = st.session_state.teacher_data['teacher_id']
    subjects = get_teacher_subjects(teacher_id)

    st.header("👥 Enrolled Students")
    if not subjects:
        st.info("No subjects created yet. Create a subject first.")
        return

    st.caption("Choose the class, then the subject. Use the search box to find one student.")
    pool = cascade_filter(subjects, 'enr', labels={'year': 'Study year'})
    if not pool:
        st.warning("No subjects match these filters.")
        return

    options = {subject_label(s): s for s in pool}
    label = st.selectbox("Subject", list(options.keys()), key='enr_subject')
    sub = options[label]
    sid = sub['subject_id']

    with st.spinner("Loading students..."):
        students = _enrolled_students(sid)
        totals = _attendance_totals(sid)

    search = st.text_input("Search student", placeholder="Type name or roll no...", key='enr_search')
    rows = student_rows(students, totals, search)

    scored = [r for r in rows if r["Attendance %"] is not None]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students shown", len(rows))
    c2.metric("With email", sum(1 for r in rows if r["Email"] != "No email"))
    c3.metric("With parent email", sum(1 for r in rows if r["Parent Email"] != "No parent email"))
    c4.metric(f"Below {ATTENDANCE_TARGET}%", sum(1 for r in scored if r["Attendance %"] < ATTENDANCE_TARGET))

    if not rows:
        st.warning("No students match this search." if search else "No students are enrolled in this subject yet.")
        return

    st.subheader(f"📋 {sub['name']} ({sub['subject_code']})")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')


def teacher_tab_attendance_records():
    st.header('Attendance Records')
    teacher_id = st.session_state.teacher_data['teacher_id']
    subjects = get_teacher_subjects(teacher_id)
    if not subjects:
        st.info("No subjects created yet.")
        return

    st.caption("Filter subjects")
    subjects = filter_rows(subjects, 'rec_sub')
    if not subjects:
        st.warning("No subjects match these filters.")
        return

    options = {"All matching subjects": None}
    options.update({subject_label(s): s for s in subjects})
    label = st.selectbox("Subject", list(options.keys()), key='rec_subject')
    chosen = subjects if options[label] is None else [options[label]]

    rows = []
    with st.spinner("Loading records..."):
        for sub in chosen:
            logs = fetch_all(lambda sid=sub['subject_id']: supabase.table('attendance_logs')
                             .select('timestamp, is_present').eq('subject_id', sid))
            groups = {}
            for l in logs:
                ts = (l.get('timestamp') or '').split('.')[0]
                g = groups.setdefault(ts, [0, 0])
                g[0] += 1
                g[1] += 1 if l.get('is_present') else 0
            for ts, (total, present) in groups.items():
                try:
                    shown = datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p")
                except Exception:
                    shown = ts or "N/A"
                rows.append({
                    "_ts": ts, "Time": shown, "Subject": sub['name'],
                    "Code": sub['subject_code'], "Course": sub.get('course') or "-",
                    "Year": sub.get('year') or "-", "Section": sub.get('section') or "-",
                    "Present": f"✅ {present} / {total} Students",
                    "Rate %": round(present / total * 100) if total else 0,
                })

    if not rows:
        st.info("No attendance records for this selection yet.")
        return
    df = pd.DataFrame(rows).sort_values("_ts", ascending=False).drop(columns="_ts")
    st.dataframe(df, hide_index=True, width='stretch')
