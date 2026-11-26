from src.services.timetable_validator import Entry, check_consecutive, validate


def E(**kw):
    base = dict(id=None, section_id=1, section_code="3D", weekday=1, period_no=3, block_len=1,
                kind="theory", subject_code="BCS 603", subject_name="CN", faculty_code="RM", room="B 202")
    base.update(kw)
    return Entry(**base)


def test_valid_theory_has_no_errors():
    assert validate(E(), []) == []


def test_activity_needs_no_faculty():
    assert validate(E(kind="activity", subject_code=None, faculty_code=None, room=None), []) == []


def test_teaching_needs_subject_and_faculty():
    assert any("faculty" in m for m in validate(E(faculty_code=None), []))
    assert any("subject" in m for m in validate(E(subject_code=None), []))


def test_day_and_period_range():
    assert validate(E(weekday=7), [])
    assert validate(E(period_no=9), [])


def test_block_cannot_run_past_last_period():
    assert any("past" in m for m in validate(E(period_no=8, block_len=2), []))


def test_section_clash():
    other = E(id=2, faculty_code="PS", room="X", subject_code="BOE 068")
    assert any("section 3D" in m for m in validate(E(), [other]))


def test_faculty_clash_across_sections():
    other = E(id=2, section_id=9, section_code="2A", room="Lab 1", subject_code="MLT")
    assert any("faculty RM" in m for m in validate(E(), [other]))


def test_room_clash():
    other = E(id=2, section_id=9, section_code="2A", faculty_code="PS", subject_code="MLT")
    assert any("room B 202" in m for m in validate(E(), [other]))


def test_lab_block_overlap_is_a_clash():
    lab = E(period_no=2, block_len=2, kind="lab", subject_code="BCAI651", faculty_code="VU", room=None)
    same_section_p3 = E(id=2, period_no=3, faculty_code="PS", room="X", subject_code="BOE 068")
    assert any("section 3D" in m for m in validate(lab, [same_section_p3]))


def test_editing_ignores_the_entry_itself():
    assert validate(E(id=5), [E(id=5)]) == []


def test_other_day_is_not_a_clash():
    other = E(id=2, weekday=2, faculty_code="RM", room="B 202", section_id=9, section_code="2A")
    assert validate(E(), [other]) == []


def test_four_teaching_periods_in_a_row_is_refused():
    others = [E(id=i, period_no=p) for i, p in ((2, 2), (3, 3), (4, 4))]
    errs = check_consecutive(E(period_no=5), others)
    assert errs and "4 periods in a row" in errs[0]


def test_lunch_break_ends_a_run():
    others = [E(id=i, period_no=p) for i, p in ((3, 3), (4, 4), (5, 5))]
    assert check_consecutive(E(period_no=6), others) == []


def test_consecutive_only_counts_the_same_faculty_and_day():
    others = [E(id=i, period_no=p, faculty_code="PS") for i, p in ((2, 2), (3, 3), (4, 4))]
    assert check_consecutive(E(period_no=5), others) == []
    other_day = [E(id=i, period_no=p, weekday=2) for i, p in ((2, 2), (3, 3), (4, 4))]
    assert check_consecutive(E(period_no=5), other_day) == []
