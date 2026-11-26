from datetime import date

import pytest

from src.services import faculty_absence_service as svc

TODAY = date(2026, 11, 24)
TEACHER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
ADMIN = 1


@pytest.fixture(autouse=True)
def _setup(fake_db):
    fake_db.tables["admins"] = [{"id": ADMIN}]
    fake_db.rpcs["faculty_absence_create"] = lambda p: 101
    fake_db.rpcs["faculty_absence_decide"] = lambda p: p["p_id"]
    return fake_db


def test_teacher_planned_request_is_pending(_setup):
    out = svc.request_absence("teacher", TEACHER, TEACHER, date(2026, 11, 25), date(2026, 11, 25),
                              "planned", None, "Medical appointment", today=TODAY)
    assert out == 101
    name, params = _setup.rpc_calls[-1]
    assert name == "faculty_absence_create"
    assert params["p_status"] == "pending" and params["p_approved_by"] is None


def test_teacher_cannot_request_for_someone_else():
    with pytest.raises(PermissionError):
        svc.request_absence("teacher", TEACHER, OTHER, date(2026, 11, 25), date(2026, 11, 25),
                            "planned", None, "Medical appointment", today=TODAY)


def test_teacher_cannot_record_emergency():
    with pytest.raises(svc.AbsenceError):
        svc.request_absence("teacher", TEACHER, TEACHER, TODAY, TODAY,
                            "emergency", None, "Fell ill", today=TODAY)


def test_admin_emergency_is_approved_and_attributed(_setup):
    svc.request_absence("admin", ADMIN, TEACHER, TODAY, TODAY,
                        "emergency", None, "Fell ill in class", today=TODAY)
    _, params = _setup.rpc_calls[-1]
    assert params["p_status"] == "approved" and params["p_approved_by"] == "1"


def test_unknown_admin_is_refused():
    with pytest.raises(PermissionError):
        svc.request_absence("admin", 99, TEACHER, TODAY, TODAY,
                            "unplanned", None, "Bus breakdown", today=TODAY)


def test_invalid_dates_raise_before_any_write(_setup):
    with pytest.raises(svc.AbsenceError):
        svc.request_absence("admin", ADMIN, TEACHER, date(2026, 11, 26), date(2026, 11, 25),
                            "planned", None, "Medical appointment", today=TODAY)
    assert _setup.rpc_calls == []


def test_clash_from_database_becomes_a_clear_message(_setup):
    def boom(params):
        raise Exception("CLASH: overlaps absence 7")
    _setup.rpcs["faculty_absence_create"] = boom
    with pytest.raises(svc.AbsenceError) as info:
        svc.request_absence("admin", ADMIN, TEACHER, TODAY, TODAY,
                            "unplanned", None, "Bus breakdown", today=TODAY)
    assert "overlaps" in str(info.value)


def test_decide_passes_the_decision_to_the_database(_setup):
    assert svc.decide_absence(ADMIN, 5, "cancelled", "") == 5
    _, params = _setup.rpc_calls[-1]
    assert params["p_new_status"] == "cancelled" and params["p_id"] == 5


def test_teacher_cannot_decide():
    with pytest.raises(PermissionError):
        svc.decide_absence(99, 5, "approved", "")


def test_teacher_list_only_returns_their_rows(_setup):
    _setup.tables["faculty_absences"] = [
        {"teacher_id": TEACHER, "start_date": "2026-11-25", "status": "pending"},
        {"teacher_id": OTHER, "start_date": "2026-11-25", "status": "pending"},
    ]
    rows = svc.list_absences(teacher_id=TEACHER)
    assert [r["teacher_id"] for r in rows] == [TEACHER]
