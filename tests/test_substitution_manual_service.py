from datetime import date

import pytest

from src.services import substitution_manual_service as msvc
from src.services.substitution_scoring import DEFAULT_WEIGHTS

ADMIN = 1
T_RM = "aaaaaaaa-0000-0000-0000-000000000001"
T_PS = "aaaaaaaa-0000-0000-0000-000000000002"
T_VK = "aaaaaaaa-0000-0000-0000-000000000003"


def _sub(**over):
    row = {"id": 1, "version_id": 9, "substitution_date": "2026-11-25", "weekday": 3,
           "period_no": 6, "section_code": "3D", "subject_code": "BCS 603", "room": "B 202",
           "original_teacher_code": "RM", "substitute_teacher_id": T_PS, "status": "assigned",
           "accepted_at": None}
    row.update(over)
    return row


def _action(fake, name):
    """Return the call for the action itself. Notice calls are made after it and are ignored here."""
    for call_name, params in reversed(fake.rpc_calls):
        if call_name == name:
            return call_name, params
    raise AssertionError(f"no call to {name}")


@pytest.fixture(autouse=True)
def _setup(fake_db):
    fake_db.tables["admins"] = [{"id": ADMIN}]
    fake_db.tables["teachers"] = [
        {"teacher_id": T_RM, "status": "approved", "name": "shivam kaushik"},
        {"teacher_id": T_PS, "status": "approved", "name": "Nikhil Tomar"},
        {"teacher_id": T_VK, "status": "approved", "name": "afsha ishtiyaq"}]
    fake_db.tables["teacher_codes"] = [
        {"code": "RM", "teacher_id": T_RM}, {"code": "PS", "teacher_id": T_PS},
        {"code": "VK", "teacher_id": T_VK}]
    fake_db.tables["faculty_subject_qualifications"] = [
        {"teacher_id": T_PS, "subject_code": "BCS 603", "level": "secondary", "is_active": True},
        {"teacher_id": T_VK, "subject_code": "BCS 603", "level": "trained", "is_active": True}]
    fake_db.tables["faculty_limits"] = [
        {"teacher_id": t, "max_daily_periods": 6, "max_weekly_periods": 20} for t in (T_RM, T_PS, T_VK)]
    fake_db.tables["faculty_unavailability"] = []
    fake_db.tables["faculty_absences"] = []
    fake_db.tables["timetable_entries"] = []
    fake_db.tables["faculty_substitutions"] = [_sub()]
    for name in ("faculty_substitution_accept", "faculty_substitution_decline",
                 "faculty_substitution_override"):
        fake_db.rpcs[name] = lambda p: None
    return fake_db


def test_only_admins_can_list_candidates():
    with pytest.raises(PermissionError):
        msvc.candidate_options(99, 9, 1)


def test_candidates_exclude_the_original_teacher_and_mark_eligibility(_setup):
    opts = msvc.candidate_options(ADMIN, 9, 1)
    assert [o["code"] for o in opts] == ["PS", "VK"]
    assert all(o["eligible"] for o in opts)


def test_override_passes_the_new_teacher_to_the_database(_setup):
    assert msvc.override_substitution(ADMIN, 1, T_VK, "Covering for illness") is True
    name, params = _action(_setup, "faculty_substitution_override")
    assert name == "faculty_substitution_override"
    assert params["p_teacher_id"] == T_VK and params["p_actor"] == "1"


def test_ineligible_override_is_refused_without_force(_setup):
    _setup.tables["faculty_limits"] = [
        {"teacher_id": T_RM, "max_daily_periods": 6, "max_weekly_periods": 20},
        {"teacher_id": T_PS, "max_daily_periods": 6, "max_weekly_periods": 20}]
    with pytest.raises(msvc.ManualError) as info:
        msvc.override_substitution(ADMIN, 1, T_VK, "Covering for illness")
    assert "Not eligible" in str(info.value)
    assert not any(n == "faculty_substitution_override" for n, _ in _setup.rpc_calls)


def test_forced_override_records_why_it_was_ineligible(_setup):
    _setup.tables["faculty_limits"] = [
        {"teacher_id": T_RM, "max_daily_periods": 6, "max_weekly_periods": 20},
        {"teacher_id": T_PS, "max_daily_periods": 6, "max_weekly_periods": 20}]
    msvc.override_substitution(ADMIN, 1, T_VK, "Covering for illness", force=True)
    _, params = _action(_setup, "faculty_substitution_override")
    assert "[forced:" in params["p_reason"]


def test_consecutive_refusal_from_database_is_clear(_setup):
    def boom(params):
        raise Exception("CONSECUTIVE: VK would teach more than 3 periods in a row")
    _setup.rpcs["faculty_substitution_override"] = boom
    with pytest.raises(msvc.ManualError) as info:
        msvc.override_substitution(ADMIN, 1, T_VK, "Covering for illness")
    assert "more than 3" in str(info.value)


def test_short_override_reason_never_reaches_the_database(_setup):
    with pytest.raises(msvc.ManualError):
        msvc.override_substitution(ADMIN, 1, T_VK, "no")
    assert _setup.rpc_calls == []


def test_teacher_accepts_their_own_assignment(_setup):
    assert msvc.accept_substitution(T_PS, 1) is True
    name, params = _setup.rpc_calls[-1]
    assert name == "faculty_substitution_accept" and params["p_teacher_id"] == T_PS


def test_teacher_cannot_accept_someone_elses_assignment(_setup):
    def boom(params):
        raise Exception("not your assignment")
    _setup.rpcs["faculty_substitution_accept"] = boom
    with pytest.raises(msvc.ManualError) as info:
        msvc.accept_substitution(T_VK, 1)
    assert "not yours" in str(info.value)


def test_decline_needs_a_reason_before_any_write(_setup):
    with pytest.raises(msvc.ManualError):
        msvc.decline_substitution(T_PS, 1, "no")
    assert _setup.rpc_calls == []


def test_decline_passes_the_reason_to_the_database(_setup):
    msvc.decline_substitution(T_PS, 1, "Medical appointment")
    name, params = _action(_setup, "faculty_substitution_decline")
    assert name == "faculty_substitution_decline"
    assert params["p_reason"] == "Medical appointment"


def test_my_substitutions_returns_only_my_assigned_rows_in_the_window(_setup):
    _setup.tables["faculty_substitutions"] = [
        _sub(id=1),
        _sub(id=2, status="proposed"),
        _sub(id=3, substitute_teacher_id=T_VK),
        _sub(id=4, substitution_date="2026-12-30"),
    ]
    rows = msvc.my_substitutions(T_PS, start=date(2026, 11, 24), days=14)
    assert [r["id"] for r in rows] == [1]
