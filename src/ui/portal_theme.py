"""Shared professional theme for the student and parent portals.
Reuses the teacher theme CSS so all three portals match. CSS only, no data access."""
import streamlit as st

from src.ui.teacher_theme import TEACHER_CSS


def inject_portal_theme():
    st.markdown("<style>" + TEACHER_CSS + "</style>", unsafe_allow_html=True)
