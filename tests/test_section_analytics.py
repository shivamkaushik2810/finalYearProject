from src.components.section_analytics import build_frame, add_group, section_summary

SUBJ = [
    {"subject_id": 1, "name": "CS", "subject_code": "C1", "section": "A", "course": "B.Tech", "year": 4, "teachers": {"name": "T1"}},
    {"subject_id": 2, "name": "ML", "subject_code": "C2", "section": None, "course": None, "year": None, "teachers": None},
]
PAIRS = [
    {"subject_id": 1, "student_id": "s1", "total": 10, "present": 9},
    {"subject_id": 1, "student_id": "s2", "total": 10, "present": 5},
    {"subject_id": 2, "student_id": "s2", "total": 0, "present": 0},
    {"subject_id": 1, "student_id": "s3", "total": None, "present": None},
]


def test_summary_counts_and_pct():
    s, stu = section_summary(add_group(build_frame(SUBJ, PAIRS), "Section only"), 75)
    a = s[s["Section"] == "Section A"].iloc[0]
    assert a["Students"] == 2 and a["Defaulters"] == 1 and a["AvgPct"] == 70.0


def test_no_na_and_missing_fields():
    s, _ = section_summary(add_group(build_frame(SUBJ, PAIRS), "Course · Year · Section"), 75)
    assert not s["AvgPct"].isna().any() and not s["DefRate"].isna().any()


def test_empty_inputs():
    df = add_group(build_frame([], []), "Section only")
    s, stu = section_summary(df, 75)
    assert s.empty and stu.empty
