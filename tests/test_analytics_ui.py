import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from seed_data import seed


def _app():
    from src.components.student_analytics_ui import student_analytics_tab
    student_analytics_tab()


def _at():
    return AppTest.from_function(_app, default_timeout=60)


@pytest.fixture(autouse=True)
def _clean():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def admin_app(fake_db):
    seed(fake_db)
    at = _at()
    at.session_state["admin_data"] = {"id": 1, "name": "Admin", "username": "admin"}
    return at


def test_requires_admin(fake_db):
    at = _at().run()
    assert [e.value for e in at.error] == ["Administrator access required."]


def test_empty_database_shows_message(fake_db):
    at = _at()
    at.session_state["admin_data"] = {"id": 1}
    at.run()
    assert not at.exception and "No students with a section" in at.info[0].value


def test_database_failure_is_reported_not_crashed(fake_db):
    seed(fake_db)
    fake_db.fail_tables.add("students")
    at = _at()
    at.session_state["admin_data"] = {"id": 1}
    at.run()
    assert not at.exception and any("Could not load sections" in e.value for e in at.error)


def test_selecting_section_and_student_shows_correct_kpis(admin_app):
    at = admin_app.run()
    assert not at.exception
    at.selectbox(key="sa_section").select_index(0).run()
    at.selectbox(key="sa_student_A").select_index(0).run()
    assert not at.exception
    values = {m.label: m.value for m in at.metric}
    assert values["Overall attendance"] == "75.0%"          # 15 of 20 classes


def test_changing_section_clears_the_student(admin_app):
    at = admin_app.run()
    at.selectbox(key="sa_section").select_index(0).run()
    at.selectbox(key="sa_student_A").select_index(0).run()
    at.selectbox(key="sa_section").select_index(1).run()
    assert at.selectbox(key="sa_student_B").value is None
    assert "Overall attendance" not in {m.label for m in at.metric}


def test_multiple_chart_types_render_together(admin_app):
    at = admin_app.run()
    at.selectbox(key="sa_section").select_index(0).run()
    at.selectbox(key="sa_student_A").select_index(0).run()
    at.multiselect(key="sa_charts_1").select("Pie").select("Stacked bar").run()
    assert not at.exception
    headings = [md.value for md in at.markdown]
    for kind in ("Bar", "Line", "Pie", "Stacked bar"):
        assert any(h.startswith(f"**{kind}:") for h in headings)
