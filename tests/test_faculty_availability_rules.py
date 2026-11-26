from datetime import date

import pytest

from src.services.faculty_availability_rules import (
    absent_periods, busy_periods, eligibility_reasons, free_periods, is_qualified,
    teaching_load, unavailable_periods, validate_limits, validate_unavailability)
from src.services.timetable_validator import Entry

DAY = date(2026, 11, 24)


def E(**kw):
    base = dict(id=None, section_id=1, section_code="3D", weekday=1, period_no=1, block_len=1,
                kind="theory", subject_code="BCS 603", subject_name="CN", faculty_code="RM", room=None)
    base.update(kw)
    return Entry(**base)


def QUAL(level="primary", active=True):
    return {"BCS 603": {"level": level, "is_active": active}}


def ELIGIBLE_KW(**over):
    kw = dict(code="RM", subject_code="BCS 603", weekday=1, period=5, on_date=DAY,
              entries=[], quals=QUAL(), rules=[], absences=[],
              limits={"max_daily": 6, "max_weekly": 20}, teacher_status="approved")
    kw.update(over)
    return kw


def test_qualification_needs_an_active_known_level():
    assert is_qualified(QUAL(), "BCS 603")
    assert not is_qualified(QUAL(active=False), "BCS 603")
    assert not is_qualified(QUAL(level="expert"), "BCS 603")
    assert not is_qualified(QUAL(), "UNKNOWN")


def test_busy_periods_cover_blocks_and_ignore_activities():
    ents = [E(period_no=3, block_len=2), E(period_no=6, kind="activity", faculty_code=None)]
    assert busy_periods(ents, "RM", 1) == {3, 4}


def test_unavailable_rule_respects_dates_and_whole_day():
    rules = [{"weekday": 1, "period_no": 2, "effective_from": date(2026, 11, 1), "effective_until": None},
             {"weekday": 1, "period_no": None, "effective_from": date(2026, 11, 1),
              "effective_until": date(2026, 11, 20)}]
    assert unavailable_periods(rules, 1, DAY) == {2}
    assert unavailable_periods(rules, 1, date(2026, 11, 10)) == set(range(1, 9)) | {2}


def test_only_approved_absences_block_periods():
    absences = [{"status": "pending", "start_date": DAY, "end_date": DAY, "periods": None},
                {"status": "approved", "start_date": DAY, "end_date": DAY, "periods": [4]}]
    assert absent_periods(absences, DAY) == {4}


def test_whole_day_approved_absence_blocks_everything():
    absences = [{"status": "approved", "start_date": DAY, "end_date": DAY, "periods": None}]
    assert free_periods("RM", 1, DAY, [], [], absences) == []


def test_free_periods_remove_busy_and_unavailable():
    ents = [E(period_no=1)]
    rules = [{"weekday": 1, "period_no": 2, "effective_from": DAY, "effective_until": None}]
    assert free_periods("RM", 1, DAY, ents, rules, []) == [3, 4, 5, 6, 7, 8]


def test_teaching_load_counts_block_length_per_day():
    ents = [E(period_no=1, block_len=2), E(period_no=4, weekday=2)]
    assert teaching_load(ents, "RM") == 3
    assert teaching_load(ents, "RM", weekday=1) == 2


def test_eligible_when_every_rule_passes():
    assert eligibility_reasons(**ELIGIBLE_KW()) == []


def test_refuses_when_already_teaching():
    reasons = eligibility_reasons(**ELIGIBLE_KW(period=1, entries=[E(period_no=1)]))
    assert any("already teaching" in r for r in reasons)


def test_refuses_unqualified_teacher():
    reasons = eligibility_reasons(**ELIGIBLE_KW(quals={}))
    assert any("not qualified" in r for r in reasons)


def test_refuses_teacher_with_no_timetable_code():
    reasons = eligibility_reasons(**ELIGIBLE_KW(code=None))
    assert reasons == ["not qualified to teach BCS 603" if not is_qualified(QUAL(), "BCS 603") else
                       "no timetable code is linked to this teacher"] or \
        "no timetable code is linked to this teacher" in reasons


def test_refuses_unapproved_teacher():
    assert any("not approved" in r for r in eligibility_reasons(**ELIGIBLE_KW(teacher_status="pending")))


def test_refuses_when_limits_are_not_set():
    assert "workload limits are not set" in eligibility_reasons(**ELIGIBLE_KW(limits=None))


def test_refuses_when_daily_limit_would_be_exceeded():
    kw = ELIGIBLE_KW(limits={"max_daily": 1, "max_weekly": 20}, entries=[E(period_no=1)], period=5)
    assert any("daily limit" in r for r in eligibility_reasons(**kw))


def test_refuses_when_weekly_limit_would_be_exceeded():
    ents = [E(period_no=1, weekday=2), E(period_no=2, weekday=3)]
    kw = ELIGIBLE_KW(limits={"max_daily": 6, "max_weekly": 2}, entries=ents, period=5)
    assert any("weekly limit" in r for r in eligibility_reasons(**kw))


def test_refuses_during_approved_absence_and_unavailability():
    absences = [{"status": "approved", "start_date": DAY, "end_date": DAY, "periods": [5]}]
    assert any("approved absence" in r for r in eligibility_reasons(**ELIGIBLE_KW(absences=absences)))
    rules = [{"weekday": 1, "period_no": 5, "effective_from": DAY, "effective_until": None}]
    assert any("unavailable" in r for r in eligibility_reasons(**ELIGIBLE_KW(rules=rules)))


def test_invalid_slot_is_refused():
    assert any("valid day" in r for r in eligibility_reasons(**ELIGIBLE_KW(period=9)))


def test_validate_unavailability_rules():
    assert validate_unavailability(1, None, "Medical leave", DAY, None) == []
    assert validate_unavailability(7, None, "Medical leave", DAY, None)
    assert validate_unavailability(1, 9, "Medical leave", DAY, None)
    assert validate_unavailability(1, 2, "ok", DAY, None)
    assert validate_unavailability(1, 2, "Medical leave", DAY, date(2026, 11, 20))


def test_validate_limits_rules():
    assert validate_limits(6, 20) == []
    assert validate_limits(9, 20)
    assert validate_limits(6, 49)
    assert validate_limits(10, 8)
