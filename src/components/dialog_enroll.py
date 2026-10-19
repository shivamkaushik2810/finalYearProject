import streamlit as st
from src.database.config import supabase
from src.database.db import enroll_student_to_subject, check_section_match
import time


def _norm(v):
    return (v or "").strip().upper()


def _enroll(student_id, sub):
    try:
        enroll_student_to_subject(student_id, sub['subject_id'])
        st.success(f"✅ Enrolled in {sub['name']}!")
        time.sleep(1)
        st.rerun()
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Could not enroll: {e}")


@st.dialog("Enroll in Subject")
def enroll_dialog():
    student_data    = st.session_state.student_data
    student_id      = student_data['student_id']
    student_section = student_data.get('section', '')

    # ── Join via code ─────────────────────────────────────────
    st.subheader("🔗 Join via Subject Code")
    st.caption("Ask your teacher for the subject code")

    join_code = st.text_input(
        "Enter Subject Code",
        placeholder="E.g. CS101",
        help="Get this code from your teacher"
    ).strip()

    if join_code:
        res = supabase.table('subjects')\
            .select('*, teachers(name)')\
            .ilike('subject_code', join_code).execute()

        if res.data:
            sub     = res.data[0]
            teacher = sub.get('teachers') or {}

            with st.container(border=True):
                st.write(f"**📚 {sub['name']}**")
                st.write(f"Code: `{sub['subject_code']}` | Section: {sub['section']}")
                st.write(f"👨‍🏫 Teacher: {teacher.get('name', 'Unknown')}")

            ok, msg = check_section_match(student_id, sub['subject_id'])
            check = supabase.table('subject_students')\
                .select('id')\
                .eq('student_id', student_id)\
                .eq('subject_id', sub['subject_id']).execute()

            if check.data:
                st.warning("⚠️ You are already enrolled in this subject!")
            elif not ok:
                st.error(f"🚫 {msg}")
            else:
                if st.button("✅ Enroll Now", type="primary", width="stretch"):
                    _enroll(student_id, sub)
        else:
            st.error("❌ Subject not found. Please check the code.")

    st.divider()

    # ── Available subjects: own section only ──────────────────
    st.subheader("📋 Available Subjects")

    if not _norm(student_section):
        st.warning("Your profile has no section, so no subjects can be shown. Please contact your administrator.")
        return

    enrolled_res = supabase.table('subject_students')\
        .select('subject_id')\
        .eq('student_id', student_id).execute()
    enrolled_ids = {e['subject_id'] for e in (enrolled_res.data or [])}

    st.caption(f"Showing subjects for your section: **{student_section}**")
    all_subs = supabase.table('subjects').select('*, teachers(name)').execute().data or []
    subjects = [s for s in all_subs if _norm(s.get('section')) == _norm(student_section)]

    if not subjects:
        st.info(f"No subjects available for Section {student_section}.")
        return

    not_enrolled = [s for s in subjects if s['subject_id'] not in enrolled_ids]
    already      = [s for s in subjects if s['subject_id'] in enrolled_ids]

    if not_enrolled:
        st.write("**🆕 Available to Join:**")
        for sub in not_enrolled:
            teacher = sub.get('teachers') or {}
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{sub['name']}**")
                    st.caption(
                        f"Code: `{sub['subject_code']}` | "
                        f"Section: {sub['section']} | "
                        f"Teacher: {teacher.get('name', 'Unknown')}"
                    )
                with col2:
                    if st.button("Enroll", key=f"enroll_{sub['subject_id']}", type="primary"):
                        _enroll(student_id, sub)
    else:
        st.info("You are enrolled in all available subjects for your section!")

    if already:
        st.divider()
        st.write("**✅ Already Enrolled:**")
        for sub in already:
            teacher = sub.get('teachers') or {}
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{sub['name']}**")
                    st.caption(
                        f"Code: `{sub['subject_code']}` | "
                        f"Section: {sub['section']} | "
                        f"Teacher: {teacher.get('name', 'Unknown')}"
                    )
                with col2:
                    st.success("✅ Enrolled")
