import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.database.attendance_status import eligible
from src.database.db import get_marks_by_subject
from src.pipelines.grading import grade_for, GRADE_ORDER
from src.components.child_overview import _classes_needed, REQUIRED_PCT
from src.services.report_export import df_pdf


def _enrolled(subject_id):
    res = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no, section, parent_email)')\
        .eq('subject_id', subject_id).execute()
    return [r['students'] for r in (res.data or []) if r.get('students')]


def _logs(subject_id):
    res = supabase.table('attendance_logs')\
        .select('student_id, is_present, timestamp, status')\
        .eq('subject_id', subject_id).execute()
    return eligible(res.data)


def _csv_button(df, label, filename, key):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv", key=key)


def _student_attendance(students, logs):
    stats = {}
    for l in logs:
        s = stats.setdefault(l['student_id'], {'total': 0, 'present': 0})
        s['total'] += 1
        if l.get('is_present'):
            s['present'] += 1
    rows = []
    for st_ in students:
        s = stats.get(st_['student_id'], {'total': 0, 'present': 0})
        pct = round(s['present'] / s['total'] * 100, 1) if s['total'] else None
        rows.append({'student': st_, 'total': s['total'], 'present': s['present'], 'pct': pct})
    return rows


# ───────────────────────── attendance ─────────────────────────

def _attendance_tab(subject, students, logs):
    if not logs:
        st.info("No attendance sessions recorded for this subject yet.")
        return

    df = pd.DataFrame(logs)
    df['ts'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    df = df.dropna(subset=['ts'])
    sessions = df.groupby('ts').agg(present=('is_present', 'sum'),
                                    total=('is_present', 'count')).reset_index()
    sessions['Attendance %'] = (sessions['present'] / sessions['total'] * 100).round(1)
    sessions = sessions.sort_values('ts')

    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions held", len(sessions))
    c2.metric("Average attendance", f"{sessions['Attendance %'].mean():.1f}%")
    c3.metric("Latest session", f"{sessions['Attendance %'].iloc[-1]:.1f}%")

    st.subheader("Attendance trend by session")
    st.line_chart(sessions.set_index('ts')['Attendance %'])

    st.subheader("Students by attendance band")
    bands = {"Below 50%": 0, "50–74%": 0, "75–89%": 0, "90%+": 0}
    for r in _student_attendance(students, logs):
        p = r['pct']
        if p is None:
            continue
        if p < 50:
            bands["Below 50%"] += 1
        elif p < 75:
            bands["50–74%"] += 1
        elif p < 90:
            bands["75–89%"] += 1
        else:
            bands["90%+"] += 1
    st.bar_chart(pd.Series(bands))


# ───────────────────────── defaulters ─────────────────────────

def _defaulters_tab(subject, students, logs, key):
    threshold = st.slider("Attendance threshold (%)", 40, 95, REQUIRED_PCT, 5, key=f"thr_{key}")
    rows = []
    for r in _student_attendance(students, logs):
        if r['pct'] is None or r['pct'] >= threshold:
            continue
        s = r['student']
        rows.append({
            "Name": s['name'], "Roll No": s.get('roll_no') or "",
            "Section": s.get('section') or "",
            "Present/Total": f"{r['present']}/{r['total']}",
            "Attendance %": r['pct'],
            "Classes needed": _classes_needed(r['present'], r['total'], threshold),
            "Parent email": s.get('parent_email') or "",
        })

    if not logs:
        st.info("No attendance recorded yet.")
        return
    if not rows:
        st.success(f"No defaulters: everyone is at or above {threshold}%.")
        return

    df = pd.DataFrame(rows).sort_values("Attendance %")
    st.warning(f"{len(df)} student(s) below {threshold}%")
    st.dataframe(df, hide_index=True, width='stretch')
    _csv_button(df, "⬇️ Download defaulters (CSV)", f"defaulters_{subject['subject_code']}.csv", f"dl_def_{key}")
    st.download_button("⬇️ Download defaulters (PDF)",
                       df_pdf(df, f"Defaulters - {subject['name']} ({subject['subject_code']})", f"Attendance below {threshold}%"),
                       file_name=f"defaulters_{subject['subject_code']}.pdf", mime="application/pdf",
                       key=f"dlp_def_{key}")


# ───────────────────────── marks ─────────────────────────

def _marks_tab(subject, key):
    marks = get_marks_by_subject(subject['subject_id'], verified_only=True)
    if not marks:
        st.info("No marks uploaded for this subject yet. Add them in the Marks tab.")
        return

    per = {}
    for m in marks:
        stu = m.get('students') or {}
        d = per.setdefault(m['student_id'], {
            'Name': stu.get('name', 'Unknown'), 'Roll No': stu.get('roll_no') or "",
            'got': 0.0, 'max': 0.0, 'by_exam': {}})
        got, mx = float(m.get('marks_obtained') or 0), float(m.get('max_marks') or 0)
        d['got'] += got
        d['max'] += mx
        e = d['by_exam'].setdefault(m.get('exam_type') or 'Other', [0.0, 0.0])
        e[0] += got
        e[1] += mx

    rows, exam_types = [], set()
    for d in per.values():
        pct = round(d['got'] / d['max'] * 100, 1) if d['max'] else 0.0
        row = {"Name": d['Name'], "Roll No": d['Roll No'],
               "Total": f"{d['got']:g}/{d['max']:g}", "Percent": pct, "Grade": grade_for(pct)}
        for et, (g, mx) in d['by_exam'].items():
            row[et] = round(g / mx * 100, 1) if mx else 0.0
            exam_types.add(et)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("Percent", ascending=False)
    pass_rate = round((df['Grade'] != 'F').mean() * 100, 1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Students graded", len(df))
    c2.metric("Class average", f"{df['Percent'].mean():.1f}%")
    c3.metric("Pass rate", f"{pass_rate}%")

    st.subheader("Grade distribution")
    counts = df['Grade'].value_counts()
    st.bar_chart(pd.Series({g: int(counts.get(g, 0)) for g in GRADE_ORDER}))

    st.subheader("Student results")
    st.caption("Exam columns show percentage per exam type; Percent is the overall total across all entries.")
    st.dataframe(df, hide_index=True, width='stretch')
    _csv_button(df, "⬇️ Download results (CSV)", f"marks_{subject['subject_code']}.csv", f"dl_marks_{key}")
    st.download_button("⬇️ Download results (PDF)",
                       df_pdf(df, f"Results - {subject['name']} ({subject['subject_code']})", "Grades computed from total marks"),
                       file_name=f"marks_{subject['subject_code']}.pdf", mime="application/pdf",
                       key=f"dlp_marks_{key}")


# ───────────────────────── announcements ─────────────────────────

def _announcements_tab(subjects, teacher_id):
    st.caption("Announcements appear on the dashboards of students enrolled in the chosen subject, and their parents.")
    options = {f"{s['name']} ({s['subject_code']})": s for s in subjects}

    with st.container(border=True):
        label = st.selectbox("Subject", list(options.keys()), key="ann_subject")
        title = st.text_input("Title", max_chars=120, key="ann_title")
        message = st.text_area("Message", max_chars=1000, key="ann_msg")
        if st.button("Post announcement", type="primary", icon=":material/campaign:", key="ann_post"):
            if not title.strip():
                st.warning("Please enter a title.")
            else:
                try:
                    supabase.table('announcements').insert({
                        'subject_id': options[label]['subject_id'],
                        'teacher_id': teacher_id,
                        'title': title.strip(),
                        'message': message.strip(),
                    }).execute()
                    st.toast("📢 Announcement posted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not post announcement: {e}")

    st.subheader("Your recent announcements")
    try:
        res = supabase.table('announcements').select('*')\
            .eq('teacher_id', teacher_id).order('created_at', desc=True).limit(15).execute()
    except Exception as e:
        st.error("Announcements table is not available. Run the announcements SQL in Supabase.")
        print(f"Announcements error: {e}")
        return

    names = {s['subject_id']: s['name'] for s in subjects}
    if not res.data:
        st.info("You haven't posted any announcements yet.")
    for a in res.data or []:
        with st.container(border=True):
            c1, c2 = st.columns([6, 1])
            with c1:
                st.write(f"**{a.get('title')}** · {names.get(a.get('subject_id'), '')}")
                if a.get('message'):
                    st.write(a['message'])
                st.caption(str(a.get('created_at', ''))[:16].replace('T', ' '))
            with c2:
                if st.button("Delete", key=f"ann_del_{a['id']}"):
                    supabase.table('announcements').delete()\
                        .eq('id', a['id']).eq('teacher_id', teacher_id).execute()
                    st.rerun()


# ───────────────────────── entry point ─────────────────────────

def teacher_analytics_tab(subjects, teacher_id):
    st.header("📊 Analytics")
    if not subjects:
        st.info("Create a subject first.")
        return

    t_att, t_def, t_marks, t_ann = st.tabs(["Attendance", "Defaulters", "Marks", "Announcements"])

    options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}

    with t_ann:
        _announcements_tab(subjects, teacher_id)

    label = st.selectbox("Subject", list(options.keys()), key="an_subject")
    subject = options[label]
    key = str(subject['subject_id'])

    students = _enrolled(subject['subject_id'])
    logs = _logs(subject['subject_id'])

    with t_att:
        _attendance_tab(subject, students, logs)
    with t_def:
        _defaulters_tab(subject, students, logs, key)
    with t_marks:
        _marks_tab(subject, key)
