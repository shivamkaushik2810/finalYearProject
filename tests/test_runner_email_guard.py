import contextlib

import pytest

from src.database import db
from src.services import weekly_report_runner as r


def _setup(monkeypatch, student):
    sent = []
    monkeypatch.delenv("REPORT_WEEK", raising=False)
    monkeypatch.setattr(r, "TEST_EMAIL_TO", None)
    monkeypatch.setattr(r, "DRY_RUN", False)
    monkeypatch.setattr(r, "get_all_enrolled_students_with_parents", lambda: [student])
    monkeypatch.setattr(r, "get_reported_student_ids", lambda ws: set())
    monkeypatch.setattr(r, "get_enrolled_subjects_map",
                        lambda: {"s1": [{"subject_id": "x", "name": "Math", "subject_code": "M1"}]})
    monkeypatch.setattr(r, "get_weekly_attendance_bulk", lambda a, b: {("s1", "x"): (2, 1)})
    monkeypatch.setattr(r, "save_weekly_reports_bulk", lambda rows: None)
    monkeypatch.setattr(r, "pooled_smtp", lambda: contextlib.nullcontext())
    monkeypatch.setattr(r, "send_weekly_parent_email", lambda **kw: sent.append(kw))
    return sent


def _student(email, parent_email):
    return {"student_id": "s1", "name": "Asha", "email": email,
            "parent_email": parent_email, "parent_name": "P"}


def test_skips_parent_email_equal_to_student_email(monkeypatch):
    sent = _setup(monkeypatch, _student("a.b@gmail.com", "ab@gmail.com"))
    assert r.send_weekly_reports_to_all_parents() == (0, 0)
    assert sent == []


def test_sends_when_emails_differ(monkeypatch):
    sent = _setup(monkeypatch, _student("asha@college.edu", "parent@gmail.com"))
    assert r.send_weekly_reports_to_all_parents() == (1, 0)
    assert len(sent) == 1
    assert sent[0]["parent_email"] == "parent@gmail.com"


def test_test_mode_still_sends_to_test_address(monkeypatch):
    sent = _setup(monkeypatch, _student("same@x.com", "same@x.com"))
    monkeypatch.setattr(r, "TEST_EMAIL_TO", "tester@example.com")
    assert r.send_weekly_reports_to_all_parents() == (1, 0)
    assert sent[0]["parent_email"] == "tester@example.com"


def test_create_student_rejects_same_mailbox():
    with pytest.raises(ValueError):
        db.create_student("X", email="a.b@gmail.com", parent_email="ab@gmail.com")
