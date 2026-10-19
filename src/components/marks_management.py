import datetime

import streamlit as st
from src.database.db import (
    add_marks, update_marks, delete_marks,
    get_marks_by_subject, get_marks_by_student
)
from src.database.config import supabase


def show_teacher_marks(subjects, teacher_id):
    st.header("📝 Subject Marks")
    st.caption("Leave a student's marks blank if they have not been entered. A typed 0 is saved as a real zero.")

    if not subjects:
        st.info("No subjects created yet. Create a subject first.")
        return

    subject_options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    selected_label = st.selectbox("Select Subject", list(subject_options.keys()), key='marks_sub')
    if not selected_label:
        return

    selected_sub = subject_options[selected_label]
    subject_id   = selected_sub['subject_id']

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        exam_type = st.selectbox(
            "Exam Type",
            ['Quiz', 'Assignment', 'Practical', 'Internal', 'Mid Term', 'End Term'],
            key='exam_type_sel'
        )
    with col2:
        max_marks = st.number_input(
            "Maximum Marks", min_value=1, max_value=1000,
            value=100, key='max_marks_input'
        )

    enrolled_res = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no, section, year)')\
        .eq('subject_id', subject_id).execute()
    enrolled = [n['students'] for n in (enrolled_res.data or []) if n.get('students')]

    if not enrolled:
        st.warning("No students enrolled in this subject.")
        return

    existing_marks = get_marks_by_subject(subject_id)
    marks_map = {f"{m['student_id']}_{m['exam_type']}": m for m in existing_marks}

    dates = [m.get('exam_date') for m in existing_marks if m['exam_type'] == exam_type and m.get('exam_date')]
    try:
        default_date = datetime.date.fromisoformat(str(dates[0])[:10]) if dates else datetime.date.today()
    except ValueError:
        default_date = datetime.date.today()
    exam_date = st.date_input("Exam date", value=default_date, key=f"exam_date_{subject_id}_{exam_type}")

    st.divider()
    st.subheader(f"👥 Enter Marks — {exam_type}")
    st.caption(f"Max Marks: {max_marks} | Subject: {selected_sub['name']}")

    marks_data = {}
    for student in enrolled:
        sid      = student['student_id']
        existing = marks_map.get(f"{sid}_{exam_type}", {})
        unverified = existing.get('entry_status') == 'unverified'

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 2, 3])
            with col1:
                st.write(f"**{student['name']}**")
                st.caption(
                    f"Roll: {student.get('roll_no','N/A')} | "
                    f"Sec: {student.get('section','N/A')} | "
                    f"Year: {student.get('year','N/A')}"
                )
                if unverified:
                    st.caption("⚠️ Unverified 0: type the real mark (0 if it is genuinely zero)")
            with col2:
                start_value = None
                if existing and not unverified:
                    start_value = min(float(existing.get('marks_obtained', 0)), float(max_marks))
                marks_input = st.number_input(
                    "Marks", min_value=0.0, max_value=float(max_marks), value=start_value,
                    placeholder="Not entered", key=f"marks_{sid}_{exam_type}", label_visibility="collapsed"
                )
            with col3:
                if marks_input is None:
                    st.write("—")
                else:
                    pct   = round((marks_input / max_marks) * 100, 1)
                    color = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"
                    st.write(f"{color} {pct}%")
            with col4:
                remarks = st.text_input(
                    "Remarks", value=existing.get('remarks') or '', placeholder="Optional remarks",
                    key=f"remarks_{sid}_{exam_type}", label_visibility="collapsed"
                )
            marks_data[sid] = {'marks': marks_input, 'remarks': remarks, 'existing_id': existing.get('id')}

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Entered Marks", type="primary", width="stretch"):
            saved, skipped = 0, 0
            for sid, data in marks_data.items():
                if data['marks'] is None:
                    skipped += 1
                    continue
                try:
                    if data['existing_id']:
                        update_marks(data['existing_id'], data['marks'], max_marks, exam_type,
                                     data['remarks'], teacher_id=teacher_id, exam_date=exam_date)
                    else:
                        add_marks(sid, subject_id, teacher_id, data['marks'], max_marks,
                                  exam_type, data['remarks'], exam_date=exam_date)
                    saved += 1
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            st.cache_data.clear()
            st.success(f"✅ Saved {saved} mark(s). {skipped} student(s) left blank (not entered).")
            st.rerun()

    with col2:
        if st.button("📊 View Summary", type="secondary", width="stretch"):
            st.session_state['show_marks_summary'] = not st.session_state.get('show_marks_summary', False)

    if st.session_state.get('show_marks_summary'):
        st.divider()
        st.subheader("📊 Marks Summary")
        all_marks = get_marks_by_subject(subject_id)

        if not all_marks:
            st.info("No marks saved yet.")
        else:
            by_exam = {}
            for m in all_marks:
                by_exam.setdefault(m['exam_type'], []).append(m)

            for et, marks_list in by_exam.items():
                with st.expander(f"📝 {et} ({len(marks_list)} students)"):
                    for m in marks_list:
                        student = m.get('students', {})
                        pct     = round((m['marks_obtained'] / m['max_marks']) * 100, 1)
                        col1, col2, col3 = st.columns([3, 2, 2])
                        with col1:
                            flag = " ⚠️ unverified" if m.get('entry_status') == 'unverified' else ""
                            st.write(f"**{student.get('name','Unknown')}**{flag}")
                        with col2:
                            st.write(f"{m['marks_obtained']}/{m['max_marks']}")
                        with col3:
                            clr = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"
                            st.write(f"{clr} {pct}%")


def show_student_marks(student_id):
    st.header("📊 My Marks")
    st.caption("View your marks for all subjects")

    marks = get_marks_by_student(student_id)

    if not marks:
        st.info("No marks available yet. Ask your teacher to upload marks.")
        return

    by_subject = {}
    for m in marks:
        sub  = m.get('subjects', {})
        name = sub.get('name', 'Unknown')
        if name not in by_subject:
            by_subject[name] = {'code': sub.get('subject_code', ''), 'marks': []}
        by_subject[name]['marks'].append(m)

    total_obtained = sum(m['marks_obtained'] for m in marks)
    total_max      = sum(m['max_marks'] for m in marks)
    overall_pct    = round((total_obtained / total_max) * 100, 1) if total_max > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Subjects", len(by_subject))
    with col2:
        st.metric("Total Marks", f"{total_obtained}/{total_max}")
    with col3:
        color = "🟢" if overall_pct >= 75 else "🟡" if overall_pct >= 50 else "🔴"
        st.metric("Overall %", f"{color} {overall_pct}%")

    st.divider()

    for sub_name, data in by_subject.items():
        sub_obtained = sum(m['marks_obtained'] for m in data['marks'])
        sub_max      = sum(m['max_marks'] for m in data['marks'])
        sub_pct      = round((sub_obtained / sub_max) * 100, 1) if sub_max > 0 else 0
        color = "🟢" if sub_pct >= 75 else "🟡" if sub_pct >= 50 else "🔴"

        with st.expander(f"{color} {sub_name} ({data['code']}) — {sub_pct}%", expanded=True):
            for m in data['marks']:
                pct  = round((m['marks_obtained'] / m['max_marks']) * 100, 1)
                col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                with col1:
                    st.write(f"📝 **{m['exam_type']}**")
                with col2:
                    st.write(f"{m['marks_obtained']}/{m['max_marks']}")
                with col3:
                    clr = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"
                    st.write(f"{clr} {pct}%")
                with col4:
                    if m.get('remarks'):
                        st.caption(m['remarks'])
