from datetime import date

import pytest

from src.services.faculty_absence_rules import (
    absences_clash, normalise_periods, periods_overlap, validate_absence)

TODAY = date(2026, 11, 24)


def test_normalise_periods():
    assert normalise_periods(None) is None
    assert normalise_periods([]) is None
    assert normalise_periods([4, 2, 2]) == [2, 4]
    with pytest.raises(ValueError):
        normalise_periods(["x"])


def test_full_day_overlaps_any_period():
    assert periods_overlap(None, [3])
    assert periods_overlap([1, 2], [2, 3])
    assert not periods_overlap([1, 2], [3, 4])


def test_clash_needs_both_dates_and_periods():
    a = {"start": date(2026, 11, 24), "end": date(2026, 11, 26), "periods": [1, 2]}
    assert absences_clash(a, {"start": date(2026, 11, 26), "end": date(2026, 11, 27), "periods": [2]})
    assert not absences_clash(a, {"start": date(2026, 11, 27), "end": date(2026, 11, 27), "periods": None})
    assert not absences_clash(a, {"start": date(2026, 11, 25), "end": date(2026, 11, 25), "periods": [3]})


def test_valid_planned_request_has_no_errors():
    assert validate_absence(date(2026, 11, 25), date(2026, 11, 25), "planned", None,
                            "Medical appointment", TODAY, False) == []


def test_end_before_start_is_refused():
    errs = validate_absence(date(2026, 11, 26), date(2026, 11, 25), "planned", None, "reason ok", TODAY, False)
    assert any("before" in e for e in errs)


def test_span_limit():
    errs = validate_absence(date(2026, 11, 25), date(2026, 12, 30), "planned", None, "reason ok", TODAY, True)
    assert any("at most 30" in e for e in errs)


def test_backdating_limit():
    assert validate_absence(date(2026, 9, 1), date(2026, 9, 1), "unplanned", None, "reason ok", TODAY, True)


def test_past_planned_refused_for_teacher_allowed_for_admin():
    past = date(2026, 11, 20)
    assert validate_absence(past, past, "planned", None, "reason ok", TODAY, False)
    assert validate_absence(past, past, "planned", None, "reason ok", TODAY, True) == []


def test_only_admin_records_emergency_or_unplanned():
    errs = validate_absence(TODAY, TODAY, "emergency", None, "reason ok", TODAY, False)
    assert any("administrator" in e for e in errs)


def test_period_range_and_reason_length():
    assert validate_absence(TODAY, TODAY, "planned", [9], "reason ok", TODAY, False)
    assert validate_absence(TODAY, TODAY, "planned", None, "no", TODAY, False)


def test_unknown_kind_is_refused():
    assert validate_absence(TODAY, TODAY, "vacation", None, "reason ok", TODAY, True)
