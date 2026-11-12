import pandas as pd

from src.components.analytics_dashboard import (
    _band, _build_session_df, _build_student_df, _overall_pct, _clean_logs,
)

ENR = [{"student_id": "a", "name": "Asha"}, {"student_id": "b", "name": "Bilal"}]


def L(sid, present, ts="2026-11-01T10:30:00"):
    return {"student_id": sid, "is_present": present, "timestamp": ts}


def test_overall_is_weighted_not_average_of_sessions():
    logs = [L("a", True, "2026-11-01T10:00:00"), L("b", True, "2026-11-01T10:00:00"),
            L("a", False, "2026-11-02T10:00:00")]
    # sessions: 100% and 0% -> naive average 50%; true = 2/3 = 66.7%
    assert _overall_pct(logs, ENR) == 66.7


def test_unenrolled_students_are_excluded():
    logs = [L("zzz", False), L("a", True)]
    assert _overall_pct(logs, ENR) == 100.0
    assert "Unknown" not in _build_student_df(logs, ENR)["name"].tolist()


def test_empty_and_missing_columns_do_not_crash():
    assert _build_session_df([], ENR).empty
    assert _build_student_df([], ENR).empty
    assert _overall_pct([], ENR) is None
    assert _build_session_df([{"student_id": "a"}], ENR).empty   # no timestamp / is_present
    assert _overall_pct([{"student_id": "a", "timestamp": "2026-11-01T10:00:00"}], ENR) == 0.0


def test_null_is_present_counts_as_absent():
    df = _clean_logs([L("a", None), L("b", True)], ENR)
    assert df["is_present"].tolist() == [False, True]


def test_fractional_seconds_do_not_split_a_session():
    logs = [L("a", True, "2026-11-01T10:30:00.123456"), L("b", False, "2026-11-01T10:30:00")]
    s = _build_session_df(logs, ENR)
    assert len(s) == 1 and s["Attendance %"].iloc[0] == 50.0


def test_unparseable_timestamps_are_dropped():
    s = _build_session_df([L("a", True, "garbage"), L("b", True)], ENR)
    assert len(s) == 1


def test_band_boundaries():
    assert _band(49.9) == "Below 50%"
    assert _band(50) == "50-75%"
    assert _band(74.9) == "50-75%"
    assert _band(75) == "75% and above"


def test_naive_values_are_ist_wall_clock_not_shifted():
    s = _build_session_df([L("a", True, "2026-11-01T10:30:00")], ENR)
    assert s["ts"].iloc[0].hour == 10 and s["ts"].iloc[0].minute == 30


def test_offset_and_naive_ist_are_one_session():
    logs = [L("a", True, "2026-11-01T10:30:00+05:30"), L("b", False, "2026-11-01T10:30:00")]
    s = _build_session_df(logs, ENR)
    assert len(s) == 1 and s["Attendance %"].iloc[0] == 50.0


def test_utc_offset_is_converted_to_ist():
    s = _build_session_df([L("a", True, "2026-11-01T05:00:00+00:00")], ENR)
    assert s["ts"].iloc[0].hour == 10 and s["ts"].iloc[0].minute == 30
