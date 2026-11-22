from datetime import date

import pytest

from src.analytics import access
from src.services import admin_service as svc


@pytest.fixture(autouse=True)
def _admin(monkeypatch, fake_db):
    monkeypatch.setattr(access.st, "session_state", {"admin_data": {"id": 1}})
    fake_db.tables["teachers"] = [
        {"teacher_id": 1, "username": "a", "name": "Asha", "email": None, "status": "approved",
         "failed_attempts": 5, "locked_until": "2026-11-22T10:00:00+00:00"},
        {"teacher_id": 2, "username": "b", "name": "Bilal", "email": None, "status": "pending",
         "failed_attempts": 0, "locked_until": None},
    ]
    yield


def test_every_action_requires_admin(monkeypatch):
    monkeypatch.setattr(access.st, "session_state", {})
    with pytest.raises(PermissionError):
        svc.list_teachers()
    with pytest.raises(PermissionError):
        svc.unlock_teacher(1)
    with pytest.raises(PermissionError):
        svc.deactivate_teacher(1)
    with pytest.raises(PermissionError):
        svc.list_corrections()


def test_unlock_clears_failures_and_lock(fake_db):
    svc.unlock_teacher(1)
    row = fake_db.tables["teachers"][0]
    assert row["failed_attempts"] == 0 and row["locked_until"] is None


def test_deactivate_and_reactivate(fake_db):
    svc.deactivate_teacher(1)
    assert fake_db.tables["teachers"][0]["status"] == "rejected"
    svc.reactivate_teacher(1)
    assert fake_db.tables["teachers"][0]["status"] == "approved"


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        svc.set_status(1, "superuser")


def test_locked_and_filtered_lists():
    assert [t["teacher_id"] for t in svc.locked_teachers()] == [1]
    assert [t["teacher_id"] for t in svc.list_teachers("pending")] == [2]


def test_quota_defaults_and_usage(fake_db, monkeypatch):
    monkeypatch.delenv("EMAIL_DAILY_LIMIT", raising=False)
    assert svc.email_quota_today() == {"sent": 0, "limit": 400, "remaining": 400}
    fake_db.tables["email_quota_usage"] = [{"day": date.today().isoformat(), "sent": 150}]
    assert svc.email_quota_today()["remaining"] == 250


def test_corrections_filtered_by_teacher(fake_db):
    fake_db.tables["attendance_audit_log"] = [
        {"id": 1, "changed_by": "1", "subject_id": "10", "student_id": "5", "old_value": True,
         "new_value": False, "reason": "x", "changed_at": "2026-11-20T10:00:00"},
        {"id": 2, "changed_by": "2", "subject_id": "11", "student_id": "6", "old_value": False,
         "new_value": True, "reason": "y", "changed_at": "2026-11-21T10:00:00"},
    ]
    assert len(svc.list_corrections()) == 2
    only = svc.list_corrections(teacher_id=1)
    assert len(only) == 1 and only[0]["id"] == 1
