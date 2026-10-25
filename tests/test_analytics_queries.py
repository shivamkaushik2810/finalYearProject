import pandas as pd
from src.database.analytics_queries import student_attendance_summary


def test_zero_total_gives_zero_pct_not_na():
    students = pd.DataFrame({"student_id": ["a", "b", "c"], "name": ["A", "B", "C"]})
    logs = pd.DataFrame({"student_id": ["a", "a", "b"],
                         "is_present": [True, False, True]})
    out = student_attendance_summary(students, logs).set_index("student_id")
    assert out.loc["a", "pct"] == 50.0
    assert out.loc["b", "pct"] == 100.0
    assert out.loc["c", "pct"] == 0.0 and out.loc["c", "total"] == 0
    assert not out["pct"].isna().any()


def test_empty_logs():
    students = pd.DataFrame({"student_id": ["a"], "name": ["A"]})
    out = student_attendance_summary(students, pd.DataFrame())
    assert out.iloc[0]["pct"] == 0.0
