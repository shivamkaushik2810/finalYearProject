import pytest

from src.services import published_timetable as pt
from src.services.timetable_validator import Entry


def E(section, faculty, period=1):
    return Entry(id=None, section_id=1, section_code=section, weekday=3, period_no=period,
                 block_len=1, kind="theory", subject_code="BCS 603", subject_name="CN",
                 faculty_code=faculty, room=None)


def test_section_code_is_built_from_year_and_section():
    assert pt.section_code_for_student("3", "D") == "3D"
    assert pt.section_code_for_student("3rd year", " d ") == "3D"


def test_missing_year_or_section_gives_no_section():
    assert pt.section_code_for_student("", "D") is None
    assert pt.section_code_for_student("3", "") is None
    assert pt.section_code_for_student(None, None) is None


def test_student_sees_only_their_section():
    entries = [E("3D", "RM"), E("3C", "RM"), E("2A", "PS")]
    assert [e.section_code for e in pt.entries_for_section(entries, "3D")] == ["3D"]


def test_teacher_sees_only_their_own_periods():
    entries = [E("3D", "RM"), E("3D", "PS", period=2), E("2A", "RM", period=3)]
    mine = pt.entries_for_teacher(entries, "RM")
    assert sorted((e.section_code, e.period_no) for e in mine) == [("2A", 3), ("3D", 1)]


def test_publish_refuses_a_non_admin(fake_db):
    fake_db.tables["admins"] = [{"id": 1}]
    with pytest.raises(PermissionError):
        pt.publish_version(99, 5)
    assert fake_db.rpc_calls == []


def test_publish_passes_the_version_and_actor(fake_db):
    fake_db.tables["admins"] = [{"id": 1}]
    fake_db.rpcs["timetable_publish"] = lambda p: None
    assert pt.publish_version(1, 5) is True
    name, params = fake_db.rpc_calls[-1]
    assert name == "timetable_publish"
    assert params["p_version_id"] == 5 and params["p_actor"] == "1"


def test_publish_explains_a_refusal_plainly(fake_db):
    fake_db.tables["admins"] = [{"id": 1}]

    def boom(params):
        raise Exception("only a draft can be published (this is published)")
    fake_db.rpcs["timetable_publish"] = boom
    with pytest.raises(pt.PublishError) as info:
        pt.publish_version(1, 5)
    assert "Only a draft" in str(info.value)
