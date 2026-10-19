import math
import pandas as pd
import pytest

from src.analytics import student_analytics as sa
from src.analytics import access

CFG = sa.AnalyticsConfig()


def att_rows(pattern, subject_id=1, name="Maths", start="2026-08-03", step_days=1):
    rows = []
    for i, p in enumerate(pattern):
        ts = (pd.Timestamp(start) + pd.Timedelta(days=i * step_days)).strftime("%Y-%m-%dT10:00:00")
        rows.append({"subject_id": subject_id, "is_present": bool(p), "timestamp": ts,
                     "subjects": {"name": name, "subject_code": "S", "teacher_id": 7, "teachers": {"name": "Dr X"}}})
    return rows


def mark_row(got, mx, subject_id=1, exam="Quiz", when=None, remarks="", student_id=1):
    r = {"student_id": student_id, "subject_id": subject_id, "marks_obtained": got, "max_marks": mx,
         "exam_type": exam, "remarks": remarks, "subjects": {"name": f"Sub{subject_id}", "subject_code": "S", "teachers": {"name": "Dr X"}}}
    if when:
        r["created_at"] = when
    return r


def test_attendance_percentage_matches_hand_calculation():
    df, dropped = sa.normalize_attendance(att_rows([1] * 15 + [0] * 5))
    s = sa.attendance_summary(df, CFG)
    assert (s["classes"], s["present"], s["pct"], dropped) == (20, 15, 75.0, 0)


def test_duplicate_records_count_once_and_invalid_timestamps_are_dropped():
    rows = att_rows([1, 0, 1]) + att_rows([1])[:1] + [{"subject_id": 1, "is_present": True, "timestamp": None, "subjects": {}}]
    df, dropped = sa.normalize_attendance(rows)
    assert len(df) == 3 and dropped == 1


def test_classes_needed_and_wilson():
    assert sa.classes_needed(10, 20, 75) == 20
    assert sa.classes_needed(15, 20, 75) == 0
    assert sa.classes_needed(0, 0, 75) is None
    assert sa.classes_needed(19, 20, 100) is None
    lo, hi = sa.wilson(15, 20)
    assert 0 < lo < 75 < hi < 100


def test_marks_are_normalised_and_missing_marks_are_not_zero():
    rows = [mark_row(18, 20), mark_row(40, 50, exam="Mid Term"), mark_row(None, 50, exam="Practical"), mark_row(60, 50, exam="Bad")]
    df, invalid, _ = sa.normalize_marks(rows, CFG)
    assert invalid == 2 and len(df) == 2
    assert sorted(df["pct"].round(1)) == [80.0, 90.0]
    assert sa.marks_summary(df, CFG)["weighted_pct"] == round(58 / 70 * 100, 1)


def test_zero_without_remarks_is_flagged_but_kept():
    df, _, _ = sa.normalize_marks([mark_row(0, 20), mark_row(0, 20, remarks="absent")], CFG)
    assert df["zero_flag"].tolist() == [True, False]


def test_standard_deviation_uses_sample_formula():
    df, _, _ = sa.normalize_marks([mark_row(v, 100, exam=f"E{i}") for i, v in enumerate([50, 60, 70, 80])], CFG)
    assert sa.marks_summary(df, CFG)["std"] == pytest.approx(12.91, abs=0.01)


def test_correlation_not_generated_without_enough_subjects():
    pairs = pd.DataFrame({"pct": [60, 70, 80, 90], "marks_pct": [50, 60, 70, 80]})
    assert sa.correlation(pairs, CFG)["status"] == "insufficient"


def test_correlation_with_enough_subjects_and_flat_series():
    pairs = pd.DataFrame({"pct": [50, 60, 70, 80, 90, 95], "marks_pct": [40, 55, 60, 72, 85, 88]})
    c = sa.correlation(pairs, CFG)
    assert c["status"] == "ok" and c["pearson"] > 0.9 and c["n"] == 6
    flat = pd.DataFrame({"pct": [70] * 5, "marks_pct": [40, 50, 60, 70, 80]})
    assert sa.correlation(flat, CFG)["status"] == "insufficient"


def test_forecast_requires_enough_weeks():
    short = pd.DataFrame({"week": pd.date_range("2026-08-03", periods=6, freq="7D"), "pct": [80] * 6})
    assert sa.forecast_attendance(short, CFG)["status"] == "insufficient"
    pct = [60 + i * 2 + (1 if i % 2 else -1) for i in range(12)]
    long = pd.DataFrame({"week": pd.date_range("2026-08-03", periods=12, freq="7D"), "pct": pct})
    f = sa.forecast_attendance(long, CFG)
    assert f["status"] == "ok" and len(f["forecast"]) == 4 and all(0 <= x["pred"] <= 100 for x in f["forecast"])


def test_probability_edge_cases_and_monotonicity():
    assert sa.prob_meet_target(2, 3, 10, 75) is None                       # too little history
    assert sa.prob_meet_target(40, 40, 5, 75) == 1.0                       # target already guaranteed
    assert sa.prob_meet_target(0, 20, 2, 75) == 0.0                        # impossible
    assert sa.prob_meet_target(16, 20, 10, 75) < sa.prob_meet_target(18, 20, 10, 75)


def test_scenarios():
    sc = sa.attendance_scenarios(15, 20, 75, [10])
    row = sc.iloc[0]
    assert row["must_attend"] == 8 and bool(row["feasible"]) and row["pct_if_all_attended"] == round(25 / 30 * 100, 1)


def test_section_comparison_needs_enough_students():
    rows = [mark_row(50 + i * 4, 100, student_id=i) for i in range(5)]
    df, _, _ = sa.normalize_marks(rows, CFG)
    assert sa.section_comparison(df, 2, CFG)["status"] == "insufficient"
    rows = [mark_row(40 + i * 4, 100, student_id=i) for i in range(12)]
    df, _, _ = sa.normalize_marks(rows, CFG)
    s = sa.section_comparison(df, 6, CFG)
    assert s["status"] == "ok" and 0 <= s["percentile"] <= 100


def test_compute_all_and_grounded_insights():
    att = att_rows([1] * 6 + [0] * 4, 1, "Maths") + att_rows([1] * 9 + [0], 2, "Physics")
    marks = [mark_row(30, 50, 1, "Mid Term", "2026-09-01T10:00:00"), mark_row(18, 20, 2, "Quiz", "2026-09-05T10:00:00"),
             mark_row(35, 50, 1, "Quiz", "2026-09-10T10:00:00")]
    subjects = [{"subject_id": 1}, {"subject_id": 2}]
    m = sa.compute_all(att, marks, [], subjects, 1, CFG)
    assert m["att"]["pct"] == 75.0 and m["att"]["classes"] == 20
    assert m["corr"]["status"] == "insufficient"                           # only 2 subjects
    assert all(i["level"] in {"good", "info", "warn", "alert"} and i["evidence"] for i in m["insights"])
    assert any("75.0%" in i["text"] for i in m["insights"])
    assert "name" not in str(sa.build_llm_payload(m)).lower().replace("subject", "")  # no identifiers in the payload


def test_marks_date_column_is_optional():
    df, _, col = sa.normalize_marks([mark_row(10, 20)], CFG)
    assert col is None and sa.latest_result(df) is None and sa.marks_trend(df, CFG)["status"] == "insufficient"


def test_unauthorised_access_is_rejected(monkeypatch):
    monkeypatch.setattr(access.st, "session_state", {})
    with pytest.raises(PermissionError):
        access.require_admin()
    monkeypatch.setattr(access.st, "session_state", {"admin_data": {"id": 1}})
    assert access.require_admin()["id"] == 1

def test_empty_attendance_input():
    df, dropped = sa.normalize_attendance([])

    assert df.empty
    assert dropped == 0


def test_empty_marks_input():
    df, invalid, date_col = sa.normalize_marks([], CFG)

    assert df.empty
    assert invalid == 0
    assert date_col is None


def test_empty_marks_summary():
    df, _, _ = sa.normalize_marks([], CFG)

    summary = sa.marks_summary(df, CFG)

    assert summary["n"] == 0


def test_filter_marks_by_subject_and_exam():
    rows = [
        mark_row(18, 20, subject_id=1, exam="Quiz"),
        mark_row(40, 50, subject_id=1, exam="Mid Term"),
        mark_row(15, 20, subject_id=2, exam="Quiz"),
    ]

    df, _, _ = sa.normalize_marks(rows, CFG)

    filtered = sa.filter_marks(
        df,
        subject_ids=[1],
        exam_types=["Quiz"],
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["subject_id"] == 1
    assert filtered.iloc[0]["pct"] == 90.0


def test_forecast_rejects_empty_data():
    empty = pd.DataFrame(columns=["week", "pct"])

    result = sa.forecast_attendance(empty, CFG)

    assert result["status"] == "insufficient"


def test_section_comparison_rejects_empty_data():
    df, _, _ = sa.normalize_marks([], CFG)

    result = sa.section_comparison(df, 1, CFG)

    assert result["status"] == "insufficient"


def test_attendance_scenarios_when_no_classes_remain():
    result = sa.attendance_scenarios(15, 20, 75, [0])

    assert not result.empty
    assert result.iloc[0]["must_attend"] == 0





# Additional tests for uncovered analytics branches

def test_risk_band_all_categories():
    assert sa.risk_band(None, 75) == "unknown"
    assert sa.risk_band(60, 75) == "critical"
    assert sa.risk_band(70, 75) == "high"
    assert sa.risk_band(77, 75) == "watch"
    assert sa.risk_band(80, 75) == "low"


def test_attendance_all_rows_invalid():
    rows = [
        {"subject_id": None, "is_present": True, "timestamp": "2026-08-03"},
        {"subject_id": 1, "is_present": True, "timestamp": None},
    ]

    df, dropped = sa.normalize_attendance(rows)

    assert df.empty
    assert dropped == 2


def test_attendance_empty_summary_tables():
    empty_att, _ = sa.normalize_attendance([])

    assert sa.by_subject_attendance(empty_att, CFG).empty
    assert sa.faculty_attendance(empty_att).empty
    assert sa.weekly_attendance(empty_att).empty
    assert sa.monthly_attendance(empty_att).empty
    assert sa.absence_streaks(empty_att).empty


def test_faculty_attendance_with_unknown_faculty():
    rows = att_rows([1, 0])
    for row in rows:
        row["subjects"]["teachers"] = {}

    df, _ = sa.normalize_attendance(rows)

    assert sa.faculty_attendance(df).empty


def test_find_date_column_candidates():
    assert sa.find_date_column([], CFG.date_columns) is None

    rows = [{"exam_date": None, "assessment_date": "2026-09-01"}]
    assert sa.find_date_column(rows, CFG.date_columns) == "assessment_date"


def test_filter_marks_by_date_range():
    rows = [
        mark_row(10, 20, when="2026-08-01"),
        mark_row(15, 20, when="2026-08-10"),
        mark_row(18, 20, when="2026-08-20"),
    ]

    df, _, _ = sa.normalize_marks(rows, CFG)

    filtered = sa.filter_marks(
        df,
        start="2026-08-05",
        end="2026-08-15",
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["pct"] == 75.0


def test_marks_summary_mode_and_consistency():
    rows = [
        mark_row(80, 100, exam="E1"),
        mark_row(80, 100, exam="E2"),
        mark_row(80, 100, exam="E3"),
        mark_row(80, 100, exam="E4"),
    ]

    df, _, _ = sa.normalize_marks(rows, CFG)
    summary = sa.marks_summary(df, CFG)

    assert summary["mode"] == 80.0
    assert summary["consistency"] == "consistent"


def test_marks_summary_outlier():
    values = [50, 51, 49, 50, 100]
    rows = [
        mark_row(v, 100, exam=f"E{i}")
        for i, v in enumerate(values)
    ]

    df, _, _ = sa.normalize_marks(rows, CFG)
    summary = sa.marks_summary(df, CFG)

    assert summary["n"] == 5
    assert isinstance(summary["outliers"], list)


def test_empty_marks_grouping_functions():
    empty, _, _ = sa.normalize_marks([], CFG)

    assert sa.by_subject_marks(empty).empty
    assert sa.by_exam_type(empty).empty

    categories = sa.marks_by_category(empty, CFG)
    assert categories["internal_external"].empty
    assert categories["theory_practical"].empty


def test_latest_result_and_declining_subjects():
    rows = [
        mark_row(90, 100, when="2026-08-01"),
        mark_row(75, 100, when="2026-08-10"),
        mark_row(60, 100, when="2026-08-20"),
    ]

    df, _, _ = sa.normalize_marks(rows, CFG)

    latest = sa.latest_result(df)
    assert latest["change"] == -15.0
    assert latest["previous_exam"] == "Quiz"

    declines = sa.declining_subjects(df)
    assert len(declines) == 1
    assert declines[0]["values"] == [90.0, 75.0, 60.0]


def test_tcrit_large_degrees_of_freedom():
    assert sa._tcrit(100) == 1.96


def test_subject_summary_when_both_inputs_empty():
    empty_att = sa.by_subject_attendance(
        pd.DataFrame(columns=sa.ATT_COLS), CFG
    )
    empty_marks = sa.by_subject_marks(
        pd.DataFrame(columns=sa.MARK_COLS)
    )

    assert sa.subject_summary(empty_att, empty_marks).empty


def test_build_completeness_with_no_enrolled_subjects():
    att, _ = sa.normalize_attendance([])
    marks, invalid, date_col = sa.normalize_marks([], CFG)

    result = sa.build_completeness(
        [], att, marks, 0, invalid, date_col, 0
    )

    assert result["selected_subjects"] == 0
    assert result["score"] is None
    assert result["with_both"] == 0


def test_private_formatting_and_wilson_zero_classes():
    from src.analytics.student_analytics import _p, wilson

    assert _p(None) == "n/a"
    assert _p(float("nan")) == "n/a"
    assert _p(12.345, 2) == "12.35"
    assert wilson(0, 0) == (None, None)


def test_marks_trend_insufficient_and_valid_cases():
    import pandas as pd
    from src.analytics.student_analytics import AnalyticsConfig, marks_trend

    cfg = AnalyticsConfig()

    # Fewer than four dated assessments
    short = pd.DataFrame({
        "when": pd.to_datetime(["2026-01-01", "2026-01-10", "2026-01-20"]),
        "pct": [50.0, 60.0, 70.0],
    })
    assert marks_trend(short, cfg)["status"] == "insufficient"

    # Four assessments, but all within less than 14 days
    narrow = pd.DataFrame({
        "when": pd.to_datetime([
            "2026-01-01", "2026-01-03", "2026-01-05", "2026-01-10"
        ]),
        "pct": [50.0, 55.0, 60.0, 65.0],
    })
    result = marks_trend(narrow, cfg)
    assert result["status"] == "insufficient"
    assert "less than 14 days" in result["reason"]

    # Four assessments spanning at least 14 days
    valid = pd.DataFrame({
        "when": pd.to_datetime([
            "2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22"
        ]),
        "pct": [40.0, 50.0, 60.0, 70.0],
    })
    result = marks_trend(valid, cfg)
    assert result["status"] == "ok"
    assert result["n"] == 4
    assert result["slope_per_30_days"] > 0


def test_attendance_marks_pairs_empty_inputs():
    import pandas as pd
    from src.analytics.student_analytics import (
        AnalyticsConfig, attendance_marks_pairs
    )

    cfg = AnalyticsConfig()
    empty = pd.DataFrame()

    assert attendance_marks_pairs(empty, empty, cfg).empty


def test_section_comparison_student_missing():
    import pandas as pd
    from src.analytics.student_analytics import (
        AnalyticsConfig, section_comparison
    )

    rows = []
    for student_id in range(10):
        rows.append({
            "student_id": student_id,
            "subject_id": "S1",
            "obtained": 70.0 + student_id,
            "max_marks": 100.0,
        })

    result = section_comparison(
        pd.DataFrame(rows), student_id="not-in-section",
        cfg=AnalyticsConfig()
    )
    assert result["status"] == "insufficient"
    assert "no marks" in result["reason"]
# Additional tests for uncovered analytics branches
import copy

import pandas as pd

from src.analytics.student_analytics import (
    AnalyticsConfig,
    generate_insights,
    compute_all,
    export_tables,
    build_llm_payload,
)


def _sample_insight_metrics():
    """Create a minimal, controlled metrics dictionary for insight tests."""
    return {
        "att": {
            "classes": 10,
            "present": 8,
            "pct": 80.0,
            "ci_low": 49.0,
            "ci_high": 94.0,
            "classes_needed": 0,
            "risk": "low",
        },
        "meta": {"period_start": None, "period_end": None},
        "subjects_below": {"attendance": [], "marks": []},
        "streaks": pd.DataFrame(
            columns=["subject_id", "subject", "longest", "current"]
        ),
        "marks": {
            "n": 2,
            "weighted_pct": 70.0,
            "mean": 70.0,
            "median": 70.0,
            "min": 60.0,
            "max": 80.0,
            "outliers": [],
            "consistency": "consistent",
            "std": 5.0,
        },
        "declines": [],
        "latest": None,
        "corr": {
            "status": "insufficient",
            "n": 0,
            "reason": "Not enough subjects.",
        },
        "section": {"status": "insufficient"},
        "completeness": {
            "zero_scores_without_remarks": 0,
            "marks_rows_excluded": 0,
            "attendance_rows_dropped": 0,
        },
    }


def test_insights_when_attendance_and_marks_are_missing():
    cfg = AnalyticsConfig()
    metrics = _sample_insight_metrics()

    metrics["att"].update(
        classes=0, present=0, pct=None, classes_needed=None, risk="unknown"
    )
    metrics["marks"] = {"n": 0, "outliers": []}

    titles = {
        item["title"] for item in generate_insights(metrics, cfg)
    }

    assert "No attendance data" in titles
    assert "No marks data" in titles


def test_insights_for_low_attendance_and_subjects():
    cfg = AnalyticsConfig()
    metrics = _sample_insight_metrics()

    metrics["att"].update(
        present=3,
        pct=30.0,
        classes_needed=18,
        risk="critical",
    )
    metrics["subjects_below"]["attendance"] = [
        {
            "subject": "Java",
            "pct": 30.0,
            "present": 3,
            "classes": 10,
            "classes_needed": 18,
        }
    ]

    titles = {
        item["title"] for item in generate_insights(metrics, cfg)
    }

    assert "Attendance is below the 75% target" in titles
    assert "1 subject(s) below the attendance target" in titles


def test_insights_for_ongoing_and_past_absence_streaks():
    cfg = AnalyticsConfig()

    ongoing = _sample_insight_metrics()
    ongoing["streaks"] = pd.DataFrame([
        {
            "subject_id": "S1",
            "subject": "Java",
            "longest": 4,
            "current": 3,
        }
    ])

    ongoing_titles = {
        item["title"] for item in generate_insights(ongoing, cfg)
    }
    assert "Ongoing consecutive absences" in ongoing_titles

    past = _sample_insight_metrics()
    past["streaks"] = pd.DataFrame([
        {
            "subject_id": "S1",
            "subject": "Java",
            "longest": 4,
            "current": 0,
        }
    ])

    past_titles = {
        item["title"] for item in generate_insights(past, cfg)
    }
    assert "Earlier absence streak" in past_titles


def test_insights_for_marks_warnings_and_outliers():
    cfg = AnalyticsConfig()
    metrics = _sample_insight_metrics()

    metrics["marks"].update(
        weighted_pct=35.0,
        std=20.0,
        consistency="highly variable",
        outliers=[
            {"subject": "Java", "exam_type": "Quiz", "pct": 5.0}
        ],
    )
    metrics["subjects_below"]["marks"] = [
        {
            "subject": "Java",
            "marks_pct": 35.0,
            "obtained": 7.0,
            "max_marks": 20.0,
        }
    ]

    titles = {
        item["title"] for item in generate_insights(metrics, cfg)
    }

    assert "Marks are below the 50% target" in titles
    assert "1 subject(s) below the marks target" in titles
    assert "Scores vary widely" in titles
    assert "Unusual scores" in titles


def test_insights_for_declining_scores_and_latest_result_drop():
    cfg = AnalyticsConfig()
    metrics = _sample_insight_metrics()

    metrics["declines"] = [
        {"subject": "Java", "values": [80.0, 60.0, 40.0]}
    ]
    metrics["latest"] = {
        "subject": "Java",
        "exam_type": "Final",
        "pct": 40.0,
        "change": -20.0,
        "previous_exam": "Midterm",
    }

    titles = {
        item["title"] for item in generate_insights(metrics, cfg)
    }

    assert "Declining scores in Java" in titles
    assert "Sharp drop in the latest result" in titles


def test_insights_for_correlation_and_section_positions():
    cfg = AnalyticsConfig()

    cases = [
        (1.2, "Above the section average"),
        (0.8, "Close to the section average"),
        (-1.5, "Below the section average"),
        (0.2, "Close to the section average"),
    ]

    for z_score, expected_title in cases:
        metrics = _sample_insight_metrics()
        metrics["corr"] = {
            "status": "ok",
            "n": 5,
            "pearson": 0.8,
            "spearman": 0.7,
            "ci_low": 0.2,
            "ci_high": 0.9,
            "strength": "strong",
        }
        metrics["section"] = {
            "status": "ok",
            "z": z_score,
            "student_pct": 80.0,
            "section_mean": 60.0,
            "section_sd": 10.0,
            "n": 20,
            "percentile": 75.0,
        }

        titles = {
            item["title"] for item in generate_insights(metrics, cfg)
        }

        assert "Attendance and marks" in titles
        assert expected_title in titles


def test_insights_for_placeholder_zeros_and_excluded_records():
    cfg = AnalyticsConfig()
    metrics = _sample_insight_metrics()

    metrics["completeness"].update(
        zero_scores_without_remarks=2,
        marks_rows_excluded=3,
        attendance_rows_dropped=1,
    )

    titles = {
        item["title"] for item in generate_insights(metrics, cfg)
    }

    assert "Possible placeholder zeros" in titles
    assert "Some records were excluded" in titles


def test_export_tables_and_llm_payload_with_empty_data():
    metrics = compute_all(
        att_rows=[],
        marks_rows=[],
        section_rows=[],
        enrolled_subjects=[],
        student_id="student-1",
    )

    tables = export_tables(metrics)
    payload = build_llm_payload(metrics)

    assert "Subject summary" in tables
    assert "Weekly attendance" in tables
    assert "Monthly attendance" in tables
    assert "Assessments" in tables
    assert "Absence streaks" in tables
    assert "Attendance records" in tables

    assert "attendance" in payload
    assert "marks" in payload
    assert "correlation" in payload
    assert "verified_insights" in payload