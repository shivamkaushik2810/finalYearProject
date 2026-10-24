import pytest

from src.database import db
from src.services import weekly_report_runner as r


def test_create_student_rejects_same_mailbox():
    with pytest.raises(ValueError):
        db.create_student("X", email="a.b@gmail.com", parent_email="ab@gmail.com")


def _patch_runner(monkeypatch, student):
    sent = []
    monkeypatch.setattr(r, "get_students_with_parents", lambda: [student])
    monkeypatch.setattr(r, "get_enrollments_for_students",
                        lambda ids: {"s1": [{"subject_id": "x", "name": "Math", "subject_code": "M1"}]})
    monkeypatch.setattr(r, "get_logs_between",
                        lambda a, b: [{"student_id": "s1", "subject_id": "x", "is_present": True}])
    monkeypatch.setattr(r, "paginate", lambda f: [])
    monkeypatch.setattr(r, "send_weekly_parent_email", lambda **kw: sent.append(kw))
    monkeypatch.setattr(r, "close_smtp", lambda: None)
    monkeypatch.setattr(r, "_flush", lambda rows: [])
    return sent


def _student(email, parent_email):
    return {"student_id": "s1", "name": "Asha", "email": email,
            "parent_email": parent_email, "parent_name": "P"}


def test_runner_skips_parent_email_equal_to_student_email(monkeypatch):
    sent = _patch_runner(monkeypatch, _student("a.b@gmail.com", "ab@gmail.com"))
    assert r.send_weekly_reports_to_all_parents() == (0, 0)
    assert sent == []


def test_runner_still_sends_when_emails_differ(monkeypatch):
    sent = _patch_runner(monkeypatch, _student("asha@college.edu", "parent@gmail.com"))
    assert r.send_weekly_reports_to_all_parents() == (1, 0)
    assert len(sent) == 1


def test_runner_accepts_force_argument(monkeypatch):
    sent = _patch_runner(monkeypatch, _student("asha@college.edu", "parent@gmail.com"))
    assert r.send_weekly_reports_to_all_parents(force=False) == (1, 0)
    assert r.send_weekly_reports_to_all_parents(force=True) == (1, 0)
