from src.services.timetable_validator import Entry
from src.services.timetable_workload import teaching_periods, workload_report


def E(**kw):
    base = dict(id=None, section_id=1, section_code="3D", weekday=1, period_no=1, block_len=1,
                kind="theory", subject_code="X", subject_name="X", faculty_code="A", room=None)
    base.update(kw)
    return Entry(**base)


def test_block_length_counts_as_periods():
    ents = [E(faculty_code="VK", kind="training", block_len=2, period_no=4), E(faculty_code="VK", period_no=6)]
    assert teaching_periods(ents) == {"VK": 3}


def test_activity_is_not_teaching_load():
    assert teaching_periods([E(kind="activity", faculty_code=None, subject_code=None)]) == {}


def test_equal_load_is_ok():
    ents = [E(faculty_code="A", period_no=1), E(faculty_code="A", period_no=2),
            E(faculty_code="B", period_no=3), E(faculty_code="B", period_no=4)]
    r = workload_report(ents, ["A", "B"])
    assert r["target_periods"] == 2
    assert all(row["status"] == "ok" for row in r["rows"])


def test_over_and_under_are_flagged():
    ents = [E(faculty_code="A", period_no=p) for p in (1, 2, 3, 4, 5, 6)] + [E(faculty_code="B", period_no=1)]
    r = workload_report(ents, ["A", "B"])
    assert {row["faculty"]: row["status"] for row in r["rows"]} == {"A": "over", "B": "under"}


def test_explicit_target_is_used():
    r = workload_report([E(faculty_code="A", period_no=1)], ["A", "C"], target_periods=5)
    assert {row["faculty"]: row["status"] for row in r["rows"]} == {"A": "under", "C": "under"}


def test_hours_from_lecture_length():
    r = workload_report([E(faculty_code="A", block_len=2)], ["A"])
    assert r["rows"][0]["hours"] == 1.67


def test_teacher_teaching_but_not_eligible_is_reported():
    r = workload_report([E(faculty_code="X")], ["A"])
    assert r["unlisted"] == ["X"]
