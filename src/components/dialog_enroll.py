import time
import streamlit as st
from src.database.config import supabase
from src.database.db import enroll_student_to_subject
from src.components.filters import can_enroll, class_label, fetch_all


def _fresh_student(student):
    """Re-reads course/year/section so a stale session can't bypass the rule."""
    try:
        rows = supabase.table('students').select('student_id, course, year, section')\
            .eq('student_id', student['student_id']).execute().data
        if rows:
            return {**student, **rows[0]}
    except Exception:
        pass
    return student


def _try_enroll(student_id, sub):
    ok = False
    try:
        enroll_student_to_subject(student_id, sub['subject_id'])
        ok = True
    except ValueError as e:
        st.error(f"🚫 {e}")
    except Exception as e:
        st.error(f"Could not enroll: {e}")
    if ok:
        st.success(f"✅ Enrolled in {sub['name']}!")
        time.sleep(1)
        st.rerun()


@st.dialog("Enroll in Subject")
def enroll_dialog():
    student = _fresh_student(st.session_state.student_data)
    student_id = student['student_id']

    st.info(f"Your class: **{class_label(student)}**\n\n"
            "You can only enroll in subjects of your own course, year and section.")

    # ── Join via code ─────────────────────────────────────────
    st.subheader("🔗 Join via Subject Code")
    join_code = st.text_input("Enter Subject Code", placeholder="E.g. CS101",
                              help="Get this code from your teacher").strip()

    if join_code:
        res = supabase.table('subjects').select('*, teachers(name)').ilike('subject_code', join_code).execute()
        if not res.data:
            st.error("❌ Subject not found. Please check the code.")
        else:
            sub = res.data[0]
            teacher = sub.get('teachers') or {}
            with st.container(border=True):
                st.write(f"**📚 {sub['name']}**")
                st.write(f"Code: `{sub['subject_code']}` | {class_label(sub)}")
                st.write(f"👨‍🏫 Teacher: {teacher.get('name', 'Unknown')}")

            allowed, why = can_enroll(sub, student)
            already = supabase.table('subject_students').select('id')\
                .eq('student_id', student_id).eq('subject_id', sub['subject_id']).execute().data
            if already:
                st.warning("⚠️ You are already enrolled in this subject!")
            elif not allowed:
                st.error(f"🚫 {why}")
            elif st.button("✅ Enroll Now", type="primary", width="stretch", key="join_code_btn"):
                _try_enroll(student_id, sub)

    st.divider()

    # ── Subjects of my own class only ─────────────────────────
    st.subheader("📋 Subjects for my class")

    enrolled_ids = {e['subject_id'] for e in fetch_all(
        lambda: supabase.table('subject_students').select('subject_id').eq('student_id', student_id))}
    all_subjects = fetch_all(lambda: supabase.table('subjects').select('*, teachers(name)'))
    mine = [s for s in all_subjects if can_enroll(s, student)[0]]

    if not mine:
        st.info(f"No subjects have been created yet for {class_label(student)}.")
        return

    not_enrolled = [s for s in mine if s['subject_id'] not in enrolled_ids]
    already_in = [s for s in mine if s['subject_id'] in enrolled_ids]

    if not_enrolled:
        st.write("**🆕 Available to Join:**")
        for sub in not_enrolled:
            teacher = sub.get('teachers') or {}
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{sub['name']}**")
                    st.caption(f"Code: `{sub['subject_code']}` | Teacher: {teacher.get('name', 'Unknown')}")
                with c2:
                    if st.button("Enroll", key=f"enroll_{sub['subject_id']}", type="primary"):
                        _try_enroll(student_id, sub)
    else:
        st.info("You are enrolled in all available subjects for your class!")

    if already_in:
        st.divider()
        st.write("**✅ Already Enrolled:**")
        for sub in already_in:
            teacher = sub.get('teachers') or {}
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{sub['name']}**")
                    st.caption(f"Code: `{sub['subject_code']}` | Teacher: {teacher.get('name', 'Unknown')}")
                with c2:
                    st.success("✅ Enrolled")
