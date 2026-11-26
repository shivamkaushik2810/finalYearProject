from datetime import date

import pytest

from src.services.substitution_scoring import (
    CRITERIA, DEFAULT_WEIGHTS, EXPERTISE_FACTOR, plan_day, score_candidate, validate_weights)
from src.services.timetable_validator import Entry

DAY = date(2026, 11, 24)
W = dict(DEFAULT_WEIGHTS)


def E(**kw):
    base = dict(id=None, section_id=1, section_code="3D", weekday=2, period_no=1, block_len=1,
                kind="theory", subject_code="BCS 601", subject_name="SE", faculty_code="ZZ", room=None)
    base.update(kw)
    return Entry(**base)


def PROF(code, subjects=("BCS 601",), level="primary", max_weekly=20, max_daily=6,
         prev=(), dept=None, pref=None, status="approved", rules=None, absences=None):
    return {"code": code, "teacher_id": code, "status": status, "department": dept,
            "quals": {s: {"level": level, "is_active": True} for s in subjects},
            "rules": rules or [], "absences": absences or [],
            "limits": {"max_daily": max_daily, "max_weekly": max_weekly},
            "previous_sections": set(prev), "preference": pref}


def SLOT(period=1, absent="AB", section="3D", subject="BCS 601", weekday=2, dept=None):
    return {"section_code": section, "subject_code": subject, "kind": "theory", "weekday": weekday,
            "period": period, "room": "B 202", "absent_code": absent, "department": dept}


def test_default_weights_total_100():
    assert sum(DEFAULT_WEIGHTS.values()) == 100 and set(DEFAULT_WEIGHTS) == set(CRITERIA)


def test_validate_weights_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_weights({k: v for k, v in W.items() if k != "preference"})
    with pytest.raises(ValueError):
        validate_weights({**W, "preference": 11})
    with pytest.raises(ValueError):
        validate_weights({**W, "expertise": -1})
    with pytest.raises(ValueError):
        validate_weights({**W, "expertise": True})
    assert validate_weights(W)["expertise"] == 40.0


def test_expertise_order():
    assert EXPERTISE_FACTOR["primary"] > EXPERTISE_FACTOR["secondary"] > EXPERTISE_FACTOR["trained"] > 0


def test_lower_workload_scores_higher():
    light = score_candidate(PROF("AA"), SLOT(), W, [])[0]
    busy_work = [E(faculty_code="BB", period_no=5), E(faculty_code="BB", period_no=6)]
    busy = score_candidate(PROF("BB"), SLOT(), W, busy_work)[0]
    assert light > busy


def test_previous_section_adds_its_weight():
    without = score_candidate(PROF("AA"), SLOT(), W, [])[0]
    with_prev = score_candidate(PROF("AA", prev=["3D"]), SLOT(), W, [])[0]
    assert round(with_prev - without, 2) == W["previous_section"]


def test_department_match_adds_its_weight():
    slot = SLOT(dept="CSE")
    same = score_candidate(PROF("AA", dept="CSE"), slot, W, [])[0]
    other = score_candidate(PROF("AA", dept="ECE"), slot, W, [])[0]
    assert round(same - other, 2) == W["department"]


def test_missing_preference_is_neutral():
    _, factors = score_candidate(PROF("AA", pref=None), SLOT(), W, [])
    assert factors["preference"] == 0.5


def test_score_is_out_of_100():
    total, factors = score_candidate(PROF("AA", prev=["3D"], dept="CSE"), SLOT(dept="CSE"), W, [])
    assert 0 <= total <= 100 and all(0 <= v <= 1 for v in factors.values())


def test_picks_highest_score_and_lists_alternatives():
    pool = {"RM": PROF("RM", prev=["3D"]), "PS": PROF("PS")}
    decisions = plan_day([SLOT()], pool, [], W, DAY)
    d = decisions[0]
    assert d["status"] == "assigned" and d["substitute_code"] == "RM"
    assert [a["code"] for a in d["alternatives"]] == ["PS"]


def test_tie_is_broken_by_code():
    pool = {"BB": PROF("BB"), "AA": PROF("AA")}
    assert plan_day([SLOT()], pool, [], W, DAY)[0]["substitute_code"] == "AA"


def test_unqualified_and_unavailable_never_selected():
    pool = {"AA": PROF("AA", subjects=()),
            "BB": PROF("BB"),
            "CC": PROF("CC")}
    entries = [E(faculty_code="BB", period_no=1)]
    d = plan_day([SLOT()], pool, entries, W, DAY)[0]
    assert d["substitute_code"] == "CC"


def test_no_eligible_teacher_is_unassigned_with_reasons():
    pool = {"AA": PROF("AA", subjects=())}
    d = plan_day([SLOT()], pool, [], W, DAY)[0]
    assert d["status"] == "unassigned" and d["substitute_code"] is None
    assert "not qualified" in d["reasons"]


def test_absent_teacher_is_never_assigned():
    pool = {"AB": PROF("AB")}
    d = plan_day([SLOT(absent="AB")], pool, [], W, DAY)[0]
    assert d["status"] == "unassigned"
    assert "no other teacher" in d["reasons"]


def test_same_teacher_not_double_booked_in_one_period():
    pool = {"RM": PROF("RM")}
    slots = [SLOT(period=1, section="3D"), SLOT(period=1, section="3E")]
    decisions = plan_day(slots, pool, [], W, DAY)
    statuses = sorted(d["status"] for d in decisions)
    assert statuses == ["assigned", "unassigned"]


def test_weekly_limit_stops_a_second_class():
    pool = {"RM": PROF("RM", max_weekly=1)}
    slots = [SLOT(period=1, section="3D"), SLOT(period=2, section="3E")]
    decisions = plan_day(slots, pool, [], W, DAY)
    assert [d["status"] for d in decisions] == ["assigned", "unassigned"]
    assert "weekly limit" in decisions[1]["reasons"]


def test_slot_with_fewest_candidates_is_decided_first():
    pool = {"RM": PROF("RM", subjects=("BCS 601", "BCS 603")),
            "PS": PROF("PS", subjects=("BCS 603",))}
    a = SLOT(period=1, section="3D", subject="BCS 601")
    b = SLOT(period=1, section="3E", subject="BCS 603")
    by_section = {d["section_code"]: d["substitute_code"]
                  for d in plan_day([b, a], pool, [], W, DAY)}
    assert by_section == {"3D": "RM", "3E": "PS"}


def test_plan_is_deterministic():
    pool = {"RM": PROF("RM", prev=["3D"]), "PS": PROF("PS"), "AA": PROF("AA")}
    slots = [SLOT(period=1, section="3D"), SLOT(period=2, section="3E")]
    assert plan_day(slots, pool, [], W, DAY) == plan_day(slots, pool, [], W, DAY)


def test_no_absent_teacher_is_ever_chosen_to_cover_another_absence():
    pool = {"AA": PROF("AA"), "BB": PROF("BB")}
    slot = SLOT(period=1, absent="AA")
    slot["absent_codes"] = {"AA", "BB"}
    d = plan_day([slot], pool, [], W, DAY)[0]
    assert d["status"] == "unassigned"
