from collections import namedtuple

from src.services import timetable_analytics as an

E = namedtuple("E", "id section_code weekday period_no block_len kind subject_code subject_name faculty_code room")


def e(i, sec="2Z", wd=1, p=1, bl=1, kind="theory", tc="TZAA", room="R1"):
    return E(i, sec, wd, p, bl, kind, "SUB" + str(i), "Subject " + str(i), tc, room)


def test_overview_counts_and_completion():
    ents = [e(1), e(2, p=2, bl=2, kind="lab", room="R2")]
    ov = an.overview(ents)
    assert ov["classes"] == 2
    assert ov["periods"] == 3
    assert ov["sections"] == 1
    assert ov["conflicts"] == 0
    assert ov["completion"] == round(3 / an.SLOTS_PER_WEEK * 100, 1)


def test_section_clash_is_found():
    ents = [e(1, p=1), e(2, p=1, tc="TZAB", room="R9")]
    assert an.clash_pairs(ents) == [(1, 2, "section")]


def test_teacher_clash_is_found_across_sections():
    ents = [e(1, sec="2Z", tc="TZAA", room="R1"), e(2, sec="3Y", tc="TZAA", room="R2")]
    assert an.clash_pairs(ents) == [(1, 2, "teacher")]


def test_room_clash_is_found():
    ents = [e(1, sec="2Z", tc="TZAA", room="R1"), e(2, sec="3Y", tc="TZAB", room="R1")]
    assert an.clash_pairs(ents) == [(1, 2, "room")]


def test_no_teacher_clash_for_activities():
    ents = [e(1, sec="2Z", kind="activity", tc=None, room=None),
            e(2, sec="3Y", kind="activity", tc=None, room=None)]
    assert an.clash_pairs(ents) == []


def test_workload_counts_block_length_and_flags_overload():
    ents = [e(1, bl=2, tc="TZAA"), e(2, p=4, tc="TZAA", sec="3Y", room="R2"),
            e(3, sec="3Z", tc="TZAB", room="R3")]
    wl = an.faculty_workload(ents, weekly_limit=2)
    first = wl[0]
    assert first["teacher"] == "TZAA" and first["periods"] == 3 and first["classes"] == 2
    assert first["overloaded"] is True
    assert an.workload_stats(wl)["overloaded"] == 1


def test_room_usage_and_empty_rooms():
    rooms, empty = an.room_usage([e(1, room="R1"), e(2, sec="3Y", room="R1", p=2)],
                                 known_rooms=("R1", "R2"))
    assert rooms[0]["room"] == "R1"
    assert rooms[0]["periods"] == 2
    assert rooms[0]["utilisation"] == round(2 / an.SLOTS_PER_WEEK * 100, 1)
    assert empty == ["R2"]


def test_section_stats_free_periods_and_practical_share():
    s = an.section_stats([e(1, bl=2), e(2, sec="2Z", p=4, kind="lab", room="R2")])[0]
    assert s["section"] == "2Z"
    assert s["periods"] == 3
    assert s["free_periods"] == an.SLOTS_PER_WEEK - 3
    assert s["lab"] == 1
    assert s["practical_share"] == 50.0


def test_import_rows_are_not_counted_as_admin_changes():
    changes = [
        {"changed_by": "import", "action": "insert", "before_json": None, "after_json": {"subject_code": "A"}},
        {"changed_by": "shivam", "action": "update", "before_json": {"subject_code": "A"}, "after_json": {}},
        {"changed_by": "shivam", "action": "swap", "before_json": {"subject_code": "B"}, "after_json": {}},
    ]
    cs = an.change_summary(changes)
    assert cs["total"] == 2
    assert cs["by_user"] == {"shivam": 2}
    assert dict(cs["most_changed"]) == {"A": 1, "B": 1}


def test_substitution_summary_counts_assigned_only():
    rows = [
        {"status": "assigned", "original_teacher_code": "RM"},
        {"status": "assigned", "original_teacher_code": "RM"},
        {"status": "unassigned", "original_teacher_code": "PS"},
    ]
    ss = an.substitution_summary(rows)
    assert ss["assigned"] == 2
    assert ss["total"] == 3
    assert ss["absent_teachers"] == [("RM", 2)]
