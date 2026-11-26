from datetime import date

import pytest

from src.services import substitution_analytics_service as AS

ADMIN = 1
TA = "aaaaaaaa-0000-0000-0000-00000000000a"


@pytest.fixture(autouse=True)
def _setup(fake_db):
    fake_db.tables["admins"] = [{"id": ADMIN}]
    fake_db.tables["teachers"] = [{"teacher_id": TA, "name": "Nikhil Tomar"}]
    fake_db.tables["faculty_substitutions"] = [
        {"id": 1, "version_id": 9, "substitution_date": "2026-11-23", "section_code": "3D",
         "subject_code": "BCS 603", "original_teacher_code": "RM", "substitute_teacher_id": TA,
         "status": "assigned", "reasons": None, "created_at": "2026-11-23T10:00:00+00:00"},
        {"id": 2, "version_id": 9, "substitution_date": "2026-11-24", "section_code": "3D",
         "subject_code": "BCS 603", "original_teacher_code": "RM", "substitute_teacher_id": None,
         "status": "unassigned", "reasons": "x", "created_at": "2026-11-24T09:00:00+00:00"},
        {"id": 3, "version_id": 8, "substitution_date": "2026-11-23", "section_code": "2A",
         "subject_code": "BCS 601", "original_teacher_code": "VU", "substitute_teacher_id": TA,
         "status": "assigned", "reasons": None, "created_at": "2026-11-23T10:00:00+00:00"},
    ]
    fake_db.tables["faculty_substitution_events"] = [
        {"substitution_id": 1, "action": "confirm", "at": "2026-11-23T10:30:00+00:00"},
        {"substitution_id": 3, "action": "confirm", "at": "2026-11-23T10:30:00+00:00"},
    ]
    return fake_db


def test_non_admin_is_refused():
    with pytest.raises(PermissionError):
        AS.load(99, 9, date(2026, 11, 1), date(2026, 11, 30))


def test_loads_only_the_requested_version_and_window(_setup):
    rows, events = AS.load(ADMIN, 9, date(2026, 11, 1), date(2026, 11, 30))
    assert sorted(r["id"] for r in rows) == [1, 2]
    assert [e["substitution_id"] for e in events] == [1]
    assert next(r for r in rows if r["id"] == 1)["substitute_name"] == "Nikhil Tomar"


def test_reversed_window_is_refused():
    with pytest.raises(ValueError):
        AS.load(ADMIN, 9, date(2026, 11, 30), date(2026, 11, 1))


def test_overlong_window_is_refused():
    with pytest.raises(ValueError):
        AS.load(ADMIN, 9, date(2025, 1, 1), date(2026, 12, 31))
