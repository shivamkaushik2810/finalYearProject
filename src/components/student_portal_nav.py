"""Student portal navigation: a sidebar with one entry per section, including the student's own
timetable. The timetable shows only the LIVE version, for the student's year and section."""
import streamlit as st

from src.components.published_timetable_ui import show_student_timetable

SECTIONS = [
    ("overview", "🏠 Overview"),
    ("subjects", "📚 My Subjects"),
    ("attendance", "📋 My Attendance"),
    ("marks", "📝 My Marks"),
    ("timetable", "🗓️ My Timetable"),
    ("leave", "📝 Leave"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]
SECTION_LABELS = [label for _, label in SECTIONS]


def student_sidebar(student):
    """Draws the sidebar and returns the key of the section the student chose."""
    with st.sidebar:
        st.markdown(f"**{student.get('name') or 'Student'}**")
        st.caption(f"Roll {student.get('roll_no') or 'N/A'} · "
                   f"Year {student.get('year') or 'N/A'} · Section {student.get('section') or 'N/A'}")
        st.divider()
        label = st.radio("Go to", SECTION_LABELS, key="student_section",
                         label_visibility="collapsed")
    return SECTION_KEYS[SECTION_LABELS.index(label)]


def student_timetable_section(student):
    st.caption("Your timetable for your year and section. It shows the live timetable, "
               "so it updates as soon as the administrator changes it.")
    show_student_timetable(student)
