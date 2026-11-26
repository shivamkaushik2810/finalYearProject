import pytest

from src.services import timetable_draft as td


def test_blank_name_is_refused_before_any_call(fake_db):
    with pytest.raises(td.DraftError):
        td.create_draft("1", 5, "   ")
    assert fake_db.rpc_calls == []


def test_creates_draft_with_trimmed_name(fake_db):
    fake_db.rpcs["timetable_create_draft"] = lambda p: 42
    assert td.create_draft("1", 5, "  sem5-copy ") == 42
    name, params = fake_db.rpc_calls[-1]
    assert name == "timetable_create_draft"
    assert params == {"p_source_version_id": 5, "p_label": "sem5-copy", "p_actor": "1"}


def test_duplicate_name_is_explained(fake_db):
    def boom(params):
        raise Exception("version label already exists")
    fake_db.rpcs["timetable_create_draft"] = boom
    with pytest.raises(td.DraftError) as info:
        td.create_draft("1", 5, "import-3D-VI")
    assert "already exists" in str(info.value)
