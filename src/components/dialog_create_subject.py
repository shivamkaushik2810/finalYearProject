import streamlit as st
from src.database.db import create_subject
from src.components.filters import COURSES, YEARS


@st.dialog("Create New Subject")
def create_subject_dialog(teacher_id):
    st.write("Enter the details of new subject")
    sub_id = st.text_input("Subject Code", placeholder="CS101")
    sub_name = st.text_input("Subject Name", placeholder="Introduction to Computer Science")

    c1, c2, c3 = st.columns(3)
    with c1:
        course = st.selectbox("Course", COURSES)
    with c2:
        year = st.selectbox("Year", YEARS)
    with c3:
        sub_section = st.text_input("Section", placeholder="A")

    if st.button("Create Subject Now", type='primary', width='stretch'):
        if sub_id and sub_name and sub_section:
            try:
                create_subject(sub_id, sub_name, sub_section.strip(), teacher_id,
                               course=course, year=year)
                st.toast("Subject Created Succesfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")
        else:
            st.warning("Please fill all the fields")
