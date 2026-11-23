from src.services import attendance_stats as S
from src.services.thresholds import ATTENDANCE_TARGET, ATTENDANCE_WARN, status_icon, status_label


def test_boundaries():
    assert status_label(75) == "Good" and status_icon(75) == "🟢"
    assert status_label(74.9) == "Average" and status_icon(74.9) == "🟡"
    assert status_label(50) == "Average"
    assert status_label(49.9) == "At risk" and status_icon(49.9) == "🔴"


def test_none_is_not_zero():
    assert status_label(None) == "No data"
    assert status_icon(None) == "⚪"


def test_attendance_stats_uses_the_same_constants():
    assert S.GOOD_PCT == ATTENDANCE_TARGET and S.AVG_PCT == ATTENDANCE_WARN
    assert S.status_for(75, 4)[0] == "good"
    assert S.status_for(60, 4)[0] == "avg"
