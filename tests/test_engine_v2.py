import pandas as pd

from src.analytics import student_analytics as sa

CFG = sa.AnalyticsConfig()
SUBJ = {"name": "Maths", "subject_code": "M", "teacher_id": 7, "teachers": {"name": "Dr X"}}


def row(i, status, present):
    return {"subject_id": 1, "is_present": present, "status": status, "subjects": SUBJ,
            "timestamp": f"2026-08-{i + 1:02d}T10:00:00"}


MIXED = [row(0, "present", True), row(1, "absent", False), row(2, "excused", False), row(3, "cancelled", False)]


def test_excused_leaves_denominator_and_cancelled_is_never_counted():
    df, _ = sa.normalize_attendance(MIXED)
    s = sa.attendance_summary(df, CFG)
    assert (s["classes"], s["present"], s["pct"]) == (2, 1, 50.0)


def test_excused_can_count_as_present_by_policy():
    df, _ = sa.normalize_attendance(MIXED, policy="present")
    assert sa.attendance_summary(df, CFG)["present"] == 2 and len(df) == 3


def test_status_counts():
    assert sa.count_status(MIXED) == {"excused": 1, "cancelled": 1}


def test_unverified_zero_is_excluded_and_counted_but_entered_zero_is_kept():
    base = {"student_id": 1, "subject_id": 1, "max_marks": 20, "exam_type": "Quiz", "remarks": "", "subjects": SUBJ}
    rows = [dict(base, marks_obtained=0, entry_status="unverified"), dict(base, marks_obtained=0, entry_status="entered", exam_type="Mid"),
            dict(base, marks_obtained=15, entry_status="entered", exam_type="End")]
    df, invalid, _ = sa.normalize_marks(rows, CFG)
    assert len(df) == 2 and invalid == 1 and sa.count_unverified(rows) == 1
    assert not df["zero_flag"].any()                       # a confirmed zero is a real zero


def test_date_falls_back_per_row():
    base = {"student_id": 1, "subject_id": 1, "marks_obtained": 10, "max_marks": 20, "remarks": "", "subjects": SUBJ}
    rows = [dict(base, exam_type="A", exam_date="2026-09-01"), dict(base, exam_type="B", created_at="2026-09-05T08:00:00+00:00")]
    df, _, col = sa.normalize_marks(rows, CFG)
    assert col == "exam_date" and df["when"].notna().all()


def test_section_comparison_from_sql_aggregates():
    agg = pd.DataFrame([{"student_id": i, "subject_id": 1, "obtained": 40 + i * 3, "max_marks": 100, "assessments": 1}
                        for i in range(12)])
    m = sa.compute_all([], [], [], [{"subject_id": 1}], 5, CFG, section_agg=agg)
    assert m["section"]["status"] == "ok" and 0 <= m["section"]["percentile"] <= 100


def test_completeness_and_insight_for_excused_cancelled_and_unverified():
    m = sa.compute_all(MIXED, [{"student_id": 1, "subject_id": 1, "marks_obtained": 0, "max_marks": 10, "exam_type": "Quiz",
                                "entry_status": "unverified", "subjects": SUBJ}], [], [{"subject_id": 1}], 1, CFG)
    comp = m["completeness"]
    assert (comp["excused_excluded"], comp["cancelled_excluded"], comp["unverified_marks"]) == (1, 1, 1)
    titles = {i["title"] for i in m["insights"]}
    assert "Excused and cancelled classes" in titles and "Unverified zero scores excluded" in titles
