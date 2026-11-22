import hashlib

import pandas as pd
import streamlit as st

from src.components.filters import subject_label
from src.database.config import supabase
from src.database.db import add_marks, update_marks, get_marks_by_subject
from src.services.marks_import import parse_marks_csv, EXAM_TYPES, TEMPLATE


def _roster(subject_id):
    res = (supabase.table('subject_students')
           .select('student_id, students(student_id, name, roll_no)')
           .eq('subject_id', subject_id).execute())
    roll_to_student = {}
    for n in (res.data or []):
        s = n.get('students') or {}
        roll = str(s.get('roll_no') or '').strip()
        if not roll:
            continue
        roll_to_student[roll] = None if roll in roll_to_student else s['student_id']
    # a roll number seen twice maps to None, so the parser reports it as shared
    return roll_to_student


def _save(subject_id, teacher_id, rows):
    existing = {(m['student_id'], m['exam_type']): m['id'] for m in get_marks_by_subject(subject_id)}
    saved = failed = 0
    for r in rows:
        try:
            key = (r['student_id'], r['exam_type'])
            if key in existing:
                update_marks(existing[key], r['marks_obtained'], r['max_marks'], r['exam_type'],
                             r['remarks'], teacher_id=teacher_id, exam_date=r['exam_date'])
            else:
                add_marks(r['student_id'], subject_id, teacher_id, r['marks_obtained'], r['max_marks'],
                          r['exam_type'], r['remarks'], exam_date=r['exam_date'])
            saved += 1
        except Exception as e:
            failed += 1
            print(f"marks import row failed: {type(e).__name__}")
    return saved, failed


def marks_import_panel(subjects, teacher_id):
    st.subheader("Import marks from a CSV file")
    st.caption("Nothing is saved until you check the file and press Save. A blank marks cell is skipped, "
               "so a missing mark never becomes zero. Existing marks for the same student and exam are updated.")
    if not subjects:
        st.info("Create a subject first.")
        return

    opts = {subject_label(s): s for s in subjects}
    label = st.selectbox("Subject", list(opts.keys()), key="mi_subject")
    subject_id = opts[label]['subject_id']

    st.download_button("Download template", TEMPLATE.encode('utf-8'),
                       file_name="marks_template.csv", mime="text/csv", key="mi_template")
    st.caption("Columns: roll_no, exam_type (" + ", ".join(EXAM_TYPES) +
               "), marks_obtained, max_marks, remarks (optional), exam_date (optional, 2026-09-01).")

    up = st.file_uploader("CSV file", type=["csv"], key=f"mi_file_{subject_id}")
    if up is None:
        return
    raw = up.getvalue()
    digest = hashlib.md5(raw).hexdigest()
    plan_key = f"mi_plan_{subject_id}_{digest}"

    if st.button("Check file", key=f"mi_check_{subject_id}_{digest}"):
        try:
            rows, errors, skipped = parse_marks_csv(raw, _roster(subject_id))
        except Exception as e:
            print(f"marks import check failed: {type(e).__name__}")
            st.error("Could not read the class list for this subject. Try again.")
            return
        st.session_state[plan_key] = (rows, errors, skipped)

    plan = st.session_state.get(plan_key)
    if not plan:
        return
    rows, errors, skipped = plan
    c1, c2, c3 = st.columns(3)
    c1.metric("Ready to save", len(rows))
    c2.metric("Blank (skipped)", skipped)
    c3.metric("Rows with errors", len(errors))

    if errors:
        st.error("Fix these lines in the file, then check again. Nothing has been saved.")
        for e in errors[:20]:
            st.write(f"- {e}")
        if len(errors) > 20:
            st.caption(f"and {len(errors) - 20} more")

    if rows:
        preview = pd.DataFrame([{"Roll No": r['roll_no'], "Exam": r['exam_type'],
                                 "Marks": r['marks_obtained'], "Max": r['max_marks'],
                                 "Date": r['exam_date'] or ""} for r in rows])
        st.dataframe(preview.head(200), hide_index=True, width="stretch")

    if rows and not errors:
        if st.button(f"Save {len(rows)} mark(s)", type="primary", key=f"mi_save_{subject_id}_{digest}"):
            saved, failed = _save(subject_id, teacher_id, rows)
            st.session_state.pop(plan_key, None)
            if failed:
                st.warning(f"Saved {saved}. {failed} row(s) could not be saved; check the subject and try again.")
            else:
                st.success(f"Saved {saved} mark(s).")
