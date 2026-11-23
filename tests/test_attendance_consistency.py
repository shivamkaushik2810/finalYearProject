from datetime import date

from src.services.attendance_summary import summarize, week_bounds

ROWS = [
    {"subject_id": 1, "timestamp": "2026-11-09T10:00:00", "is_present": True,  "status": "present",   "is_excused": False},
    {"subject_id": 1, "timestamp": "2026-11-10T10:00:00", "is_present": False, "status": "absent",    "is_excused": False},
    {"subject_id": 1, "timestamp": "2026-11-11T10:00:00", "is_present": False, "status": "excused",   "is_excused": True},
    {"subject_id": 1, "timestamp": "2026-11-12T10:00:00", "is_present": False, "status": "cancelled", "is_excused": False},
]


def test_cancelled_and_excused_rules():
    s = summarize(ROWS)
    assert (s["present"], s["total"], s["pct"]) == (1, 2, 50.0)


def test_window_restricts_rows():
    s = summarize(ROWS, start=date(2026, 11, 10), end=date(2026, 11, 15))
    assert s["total"] == 1 and s["pct"] == 0.0


def test_no_counted_classes_is_none_not_zero():
    assert summarize([])["pct"] is None


def test_same_class_counts_once():
    assert summarize(ROWS[:1] + [dict(ROWS[0])])["total"] == 1


def test_week_bounds():
    assert week_bounds(date(2026, 11, 12)) == (date(2026, 11, 9), date(2026, 11, 15))
