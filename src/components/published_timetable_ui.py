"""Read-only timetable views for teachers, students and parents. Show only the published version."""
import streamlit as st

from src.components.timetable_views import all_sections_html, teacher_matrix_html
from src.services import published_timetable as pt
from src.components.live_timetable_fragment import live_timetable
from src.services.timetable_service import list_period_slots


def _header(version):
    when = str(version.get("published_at") or "")[:16].replace("T", " ")
    st.caption(f"Published timetable: {version['label']}" + (f", published {when}" if when else ""))


def show_my_timetable(teacher_id):
    st.subheader("🗓️ My timetable")
    version = pt.published_version()
    if not version:
        st.info("The timetable has not been published yet. It will appear here once the administrator publishes it.")
        return
    code = pt.teacher_code_for(teacher_id)
    if not code:
        st.warning("Your timetable code is not linked yet. Ask the administrator to link it.")
        return
    _header(version)

    def _draw(v):
        entries = pt.entries_for_teacher(pt.published_entries(v["id"]), code)
        if not entries:
            st.info("You have no teaching periods in the published timetable.")
            return
        st.markdown(teacher_matrix_html(entries, teachers=[code]), unsafe_allow_html=True)
        st.markdown("**Weekly grid**")
        st.markdown(all_sections_html(entries, list_period_slots()), unsafe_allow_html=True)

    live_timetable(f"teacher_{teacher_id}", _draw)


def show_student_timetable(student):
    st.subheader("🗓️ Timetable")
    version = pt.published_version()
    if not version:
        st.info("The timetable has not been published yet.")
        return
    section = pt.section_code_for_student(student.get("year"), student.get("section"))
    if not section:
        st.warning("Your year or section is not set. Ask your administrator to update your profile.")
        return
    _header(version)

    def _draw(v):
        entries = pt.entries_for_section(pt.published_entries(v["id"]), section)
        if not entries:
            st.info(f"No classes for section {section} in the published timetable yet.")
            return
        st.markdown(all_sections_html(entries, list_period_slots()), unsafe_allow_html=True)

    live_timetable(f"student_{student.get('student_id')}", _draw)
