from datetime import date

from src.services.substitution_scoring import DEFAULT_WEIGHTS, plan_day
from src.services.timetable_validator import Entry

DAY = date(2026, 11, 25)   # Wednesday
W = dict(DEFAULT_WEIGHTS)


def PROF(code, level="primary", prev=()):
    return {"code": code, "teacher_id": code, "status": "approved", "department": None,
            "quals": {"BCS 603": {"level": level, "is_active": True}},
            "rules": [], "absences": [], "limits": {"max_daily": 6, "max_weekly": 20},
            "previous_sections": set(prev), "preference": None}


def SLOT(period=6, excluded=()):
    return {"section_code": "3D", "subject_code": "BCS 603", "kind": "theory", "weekday": 3,
            "period": period, "room": "B 202", "absent_code": "RM", "department": None,
            "excluded": set(excluded)}


def E(period, code, weekday=3):
    return Entry(id=None, section_id=1, section_code="3D", weekday=weekday, period_no=period,
                 block_len=1, kind="theory", subject_code="X", subject_name="X",
                 faculty_code=code, room=None)


def test_excluded_teacher_is_not_chosen_for_that_class():
    pool = {"PS": PROF("PS", level="secondary", prev=["3D"]), "AA": PROF("AA")}
    d = plan_day([SLOT(excluded=["PS"])], pool, [], W, DAY)[0]
    assert d["substitute_code"] == "AA"


def test_excluded_for_every_candidate_is_unassigned_with_reason():
    pool = {"PS": PROF("PS")}
    d = plan_day([SLOT(excluded=["PS"])], pool, [], W, DAY)[0]
    assert d["status"] == "unassigned"
    assert "declined or overridden" in d["reasons"]


def test_exclusion_applies_only_to_its_own_class():
    pool = {"PS": PROF("PS")}
    slots = [SLOT(period=6, excluded=["PS"]), SLOT(period=7)]
    decisions = {d["period"]: d for d in plan_day(slots, pool, [], W, DAY)}
    assert decisions[6]["status"] == "unassigned"
    assert decisions[7]["substitute_code"] == "PS"


def test_fourth_consecutive_period_is_refused_and_another_teacher_chosen():
    busy = [E(1, "PS"), E(2, "PS"), E(3, "PS")]
    pool = {"PS": PROF("PS", level="secondary"), "AA": PROF("AA")}
    d = plan_day([SLOT(period=4)], pool, busy, W, DAY)[0]
    assert d["substitute_code"] == "AA"
