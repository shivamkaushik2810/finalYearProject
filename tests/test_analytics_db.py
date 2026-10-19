import datetime as dt

import pytest
import streamlit as st

from seed_data import seed
from src.analytics import access
from src.database import analytics_db as adb


@pytest.fixture(autouse=True)
def _setup(fake_db, monkeypatch):
    st.cache_data.clear()
    monkeypatch.setattr(access.st, "session_state", {"admin_data": {"id": 1}})
    seed(fake_db)
    yield
    st.cache_data.clear()


def test_sections_are_normalised_and_counted():
    secs = adb.get_sections()
    assert list(secs) == ["A", "B"]
    assert secs["A"]["count"] == 2 and set(secs["A"]["raw"]) == {"a", "A "}


def test_sections_use_sql_function_when_present(fake_db):
    fake_db.rpcs["analytics_sections"] = lambda p: [{"key": "Z", "raw": ["z"], "count": 5}]
    assert adb.get_sections() == {"Z": {"raw": ["z"], "count": 5}}


def test_requires_admin(monkeypatch):
    monkeypatch.setattr(access.st, "session_state", {})
    with pytest.raises(PermissionError):
        adb.get_sections()


def test_students_filtered_by_section_and_unknown_section_rejected():
    assert [s["name"] for s in adb.get_students("A")] == ["Aarav", "Diya"]
    with pytest.raises(ValueError):
        adb.get_students("Q")


def test_student_from_another_section_is_rejected():
    with pytest.raises(PermissionError):
        adb.get_attendance("A", 3)
    with pytest.raises(PermissionError):
        adb.get_marks("A", 3)
    with pytest.raises(PermissionError):
        adb.get_enrolled_subjects("A", 3)


def test_attendance_filters_and_subject_authorisation():
    assert len(adb.get_attendance("A", 1)) == 20
    assert len(adb.get_attendance("A", 1, [10], dt.date(2026, 8, 5), dt.date(2026, 8, 7))) == 3
    assert adb.get_attendance("A", 1, [99]) == []          # not enrolled in 99


def test_invalid_dates_are_rejected():
    with pytest.raises(ValueError):
        adb.get_attendance("A", 1, None, dt.date(2026, 9, 1), dt.date(2026, 8, 1))
    with pytest.raises(ValueError):
        adb.get_attendance("A", 1, None, "yesterday", None)


def test_pagination_reads_every_row(fake_db, monkeypatch):
    monkeypatch.setattr(adb, "PAGE", 10)
    seed(fake_db, n_classes=25)
    fake_db.calls.clear()
    assert len(adb.get_attendance("A", 1)) == 25
    assert fake_db.calls.count(("attendance_logs", "select")) == 3


def test_section_marks_are_read_in_chunks(fake_db, monkeypatch):
    monkeypatch.setattr(adb, "CHUNK", 2)
    fake_db.tables["students"] = [{"student_id": i, "name": f"S{i}", "roll_no": f"R{i}", "section": "A"} for i in range(1, 6)]
    st.cache_data.clear()
    fake_db.calls.clear()
    adb.get_section_marks("A")
    assert fake_db.calls.count(("marks", "select")) == 3


def test_sql_aggregation_path_and_parameters(fake_db):
    fake_db.rpcs["analytics_section_marks"] = lambda p: [
        {"student_id": 1, "subject_id": 10, "obtained": 50.0, "max_marks": 100.0, "assessments": 2}]
    df = adb.get_section_marks_agg("A", [10], None, None, None)
    assert list(df["obtained"]) == [50.0]
    name, params = fake_db.rpc_calls[-1]
    assert name == "analytics_section_marks" and params["p_section"] == "A" and params["p_subject_ids"] == [10]
    assert "p_start" not in params and "p_exam_types" not in params       # null parameters are omitted


def test_sql_aggregation_unavailable_returns_none():
    assert adb.get_section_marks_agg("A") is None


def test_sql_aggregation_rejects_unknown_section():
    with pytest.raises(ValueError):
        adb.get_section_marks_agg("Q")
