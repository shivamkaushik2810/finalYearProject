from datetime import date

import pytest

from src.services import substitution_service as svc
from src.services.substitution_scoring import DEFAULT_WEIGHTS

ADMIN = 1
DAY = date(2026, 11, 24)            # Tuesday, weekday 2
SUNDAY = date(2026, 11, 29)
T_AB = "aaaaaaaa-0000-0000-0000-000000000001"
T_RM = "aaaaaaaa-0000-0000-0000-000000000002"
T_PS = "aaaaaaaa-0000-0000-0000-000000000003"


@pytest.fixture(autouse=True)
def _setup(fake_db):
    fake_db.tables["admins"] = [{"id": ADMIN}]
    fake_db.tables["teacher_codes"] = [
        {"code": "AB", "teacher_id": T_AB}, {"code": "RM", "teacher_id": T_RM},
        {"code": "PS", "teacher_id": T_PS}]
    fake_db.tables["teachers"] = [
        {"teacher_id": T_AB, "status": "approved"}, {"teacher_id": T_RM, "status": "approved"},
        {"teacher_id": T_PS, "status": "approved"}]
    fake_db.tables["faculty_subject_qualifications"] = [
        {"teacher_id": T_RM, "subject_code": "BCS 601", "level": "primary", "is_active": True},
        {"teacher_id": T_PS, "subject_code": "BCS 601", "level": "primary", "is_active": True}]
    fake_db.tables["faculty_limits"] = [
        {"teacher_id": t, "max_daily_periods": 6, "max_weekly_periods": 20} for t in (T_AB, T_RM, T_PS)]
    fake_db.tables["faculty_absences"] = [
        {"teacher_id": T_AB, "status": "approved", "start_date": "2026-11-24",
         "end_date": "2026-11-24", "periods": None}]
    fake_db.tables["faculty_unavailability"] = []
    fake_db.tables["substitution_weights"] = [
        {"criterion": k, "weight": v} for k, v in DEFAULT_WEIGHTS.items()]
    fake_db.tables["timetable_entries"] = [
        {"id": 1, "version_id": 9, "section_id": 1, "weekday": 2, "period_no": 1, "block_len": 1,
         "kind": "theory", "subject_code": "BCS 601", "subject_name": "SE", "faculty_code": "AB",
         "room": "B 202", "sections": {"code": "3D"}},
        {"id": 2, "version_id": 9, "section_id": 2, "weekday": 2, "period_no": 5, "block_len": 1,
         "kind": "theory", "subject_code": "BCS 603", "subject_name": "CN", "faculty_code": "RM",
         "room": "B 202", "sections": {"code": "3E"}},
        {"id": 3, "version_id": 9, "section_id": 1, "weekday": 5, "period_no": 2, "block_len": 1,
         "kind": "theory", "subject_code": "BCS 603", "subject_name": "CN", "faculty_code": "RM",
         "room": "B 202", "sections": {"code": "3D"}},
        {"id": 4, "version_id": 9, "section_id": 3, "weekday": 2, "period_no": 3, "block_len": 1,
         "kind": "theory", "subject_code": "BCS 601", "subject_name": "SE", "faculty_code": "PS",
         "room": "B 203", "sections": {"code": "2A"}}]
    fake_db.tables["faculty_substitutions"] = []
    fake_db.rpcs["faculty_substitution_save_plan"] = lambda p: len(p["p_rows"])
    fake_db.rpcs["faculty_substitution_confirm"] = lambda p: p["p_id"]
    return fake_db


def test_plan_assigns_previous_section_teacher_and_saves_as_proposed(_setup):
    out = svc.plan_substitutions(ADMIN, 9, DAY)
    assert out["assigned"] == 1 and out["unassigned"] == 0 and out["saved"] == 1
    name, params = _setup.rpc_calls[-1]
    assert name == "faculty_substitution_save_plan"
    row = params["p_rows"][0]
    assert row["status"] == "proposed"
    assert row["substitute_teacher_id"] == T_RM
    assert row["absent_code"] == "AB" and row["period"] == 1


def test_no_absences_saves_an_empty_plan_to_clear_old_proposals(_setup):
    _setup.tables["faculty_absences"] = []
    out = svc.plan_substitutions(ADMIN, 9, DAY)
    assert out["slots"] == 0
    assert _setup.rpc_calls[-1][1]["p_rows"] == []


def test_sunday_makes_no_changes(_setup):
    out = svc.plan_substitutions(ADMIN, 9, SUNDAY)
    assert out["note"] == "no classes on Sunday"
    assert _setup.rpc_calls == []


def test_non_admin_cannot_plan(_setup):
    with pytest.raises(PermissionError):
        svc.plan_substitutions(99, 9, DAY)
    assert _setup.rpc_calls == []


def test_absent_teacher_without_code_is_reported_not_covered(_setup):
    _setup.tables["teacher_codes"] = [{"code": "RM", "teacher_id": T_RM}, {"code": "PS", "teacher_id": T_PS}]
    out = svc.plan_substitutions(ADMIN, 9, DAY)
    assert any("no timetable code" in w for w in out["warnings"])
    assert out["slots"] == 0


def test_already_assigned_slot_is_not_replanned(_setup):
    _setup.tables["faculty_substitutions"] = [{
        "version_id": 9, "substitution_date": "2026-11-24", "weekday": 2, "period_no": 1,
        "section_code": "3D", "subject_code": "BCS 601", "room": "B 202",
        "substitute_teacher_id": T_PS, "status": "assigned"}]
    out = svc.plan_substitutions(ADMIN, 9, DAY)
    assert out["slots"] == 0
    assert _setup.rpc_calls[-1][1]["p_rows"] == []


def test_confirm_moves_a_proposal_to_assigned(_setup):
    assert svc.confirm_substitution(ADMIN, 5) is True
    name, params = _setup.rpc_calls[-1]
    assert name == "faculty_substitution_confirm" and params["p_id"] == 5


def test_confirm_reports_a_double_booking_plainly(_setup):
    def boom(params):
        raise Exception("duplicate key value violates unique constraint "
                        "faculty_substitutions_no_double_booking")
    _setup.rpcs["faculty_substitution_confirm"] = boom
    with pytest.raises(svc.SubstitutionError) as info:
        svc.confirm_substitution(ADMIN, 5)
    assert "already covers another class" in str(info.value)


def test_confirm_reports_a_wrong_status_plainly(_setup):
    def boom(params):
        raise Exception("cannot confirm a assigned substitution")
    _setup.rpcs["faculty_substitution_confirm"] = boom
    with pytest.raises(svc.SubstitutionError) as info:
        svc.confirm_substitution(ADMIN, 5)
    assert "Only a proposed" in str(info.value)


def test_non_admin_cannot_confirm(_setup):
    with pytest.raises(PermissionError):
        svc.confirm_substitution(99, 5)
