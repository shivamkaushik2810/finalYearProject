from datetime import date

import pytest

from src.services import faculty_availability_service as svc
from src.services.faculty_availability_rules import PlanningError

TEACHER = "11111111-1111-1111-1111-111111111111"
ADMIN = 1
DAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def _setup(fake_db):
    fake_db.tables["admins"] = [{"id": ADMIN}]
    fake_db.tables["teachers"] = [{"teacher_id": TEACHER, "status": "approved"}]
    fake_db.tables["teacher_codes"] = [{"teacher_id": TEACHER, "code": "RM"}]
    fake_db.tables["faculty_subject_qualifications"] = [
        {"teacher_id": TEACHER, "subject_code": "BCS 603", "level": "primary", "is_active": True}]
    fake_db.tables["faculty_limits"] = [
        {"teacher_id": TEACHER, "max_daily_periods": 6, "max_weekly_periods": 20}]
    fake_db.tables["faculty_unavailability"] = []
    fake_db.tables["faculty_absences"] = []
    fake_db.tables["timetable_entries"] = [
        {"id": 1, "version_id": 9, "section_id": 1, "weekday": 1, "period_no": 1, "block_len": 1,
         "kind": "theory", "subject_code": "BCS 601", "subject_name": "SE",
         "faculty_code": "RM", "room": "B 202"}]
    fake_db.rpcs["faculty_qualification_set"] = lambda p: None
    fake_db.rpcs["faculty_unavailability_add"] = lambda p: 7
    fake_db.rpcs["faculty_limits_set"] = lambda p: None
    return fake_db


def test_eligible_teacher_has_free_periods(_setup):
    out = svc.check_eligibility(ADMIN, 9, TEACHER, "BCS 603", 1, 5, DAY)
    assert out["eligible"] is True
    assert 5 in out["free_periods"] and 1 not in out["free_periods"]


def test_busy_period_is_refused(_setup):
    out = svc.check_eligibility(ADMIN, 9, TEACHER, "BCS 603", 1, 1, DAY)
    assert out["eligible"] is False
    assert any("already teaching" in r for r in out["reasons"])


def test_teacher_without_code_is_refused(_setup):
    _setup.tables["teacher_codes"] = []
    out = svc.check_eligibility(ADMIN, 9, TEACHER, "BCS 603", 1, 5, DAY)
    assert any("no timetable code" in r for r in out["reasons"])


def test_non_admin_cannot_check(_setup):
    with pytest.raises(PermissionError):
        svc.check_eligibility(99, 9, TEACHER, "BCS 603", 1, 5, DAY)


def test_unknown_teacher_raises(_setup):
    with pytest.raises(PlanningError):
        svc.check_eligibility(ADMIN, 9, "99999999-9999-9999-9999-999999999999", "BCS 603", 1, 5, DAY)


def test_set_qualification_passes_values_to_database(_setup):
    svc.set_qualification(ADMIN, TEACHER, "  BCS 603 ", "secondary", True)
    name, params = _setup.rpc_calls[-1]
    assert name == "faculty_qualification_set"
    assert params["p_subject_code"] == "BCS 603" and params["p_level"] == "secondary"


def test_set_qualification_rejects_unknown_level_before_writing(_setup):
    with pytest.raises(PlanningError):
        svc.set_qualification(ADMIN, TEACHER, "BCS 603", "expert", True)
    assert _setup.rpc_calls == []


def test_add_unavailability_validates_before_writing(_setup):
    with pytest.raises(PlanningError):
        svc.add_unavailability(ADMIN, TEACHER, 7, None, "Medical leave", DAY)
    assert _setup.rpc_calls == []


def test_add_unavailability_writes_once(_setup):
    assert svc.add_unavailability(ADMIN, TEACHER, 1, 2, "Medical leave", DAY) == 7
    assert _setup.rpc_calls[-1][0] == "faculty_unavailability_add"


def test_set_limits_rejects_daily_above_weekly(_setup):
    with pytest.raises(PlanningError):
        svc.set_limits(ADMIN, TEACHER, 10, 8)
    assert _setup.rpc_calls == []


def test_database_clash_becomes_a_plain_message(_setup):
    def boom(params):
        raise Exception("CLASH: overlaps")
    _setup.rpcs["faculty_limits_set"] = boom
    with pytest.raises(PlanningError) as info:
        svc.set_limits(ADMIN, TEACHER, 6, 20)
    assert "overlaps" in str(info.value)
