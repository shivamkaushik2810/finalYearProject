import smtplib
import sys
import threading
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def ms(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.pkl"))
    import importlib
    from src.pipelines import model_store
    importlib.reload(model_store)
    return model_store


def _model():
    return {"clf": "x", "X": [[0.0, 0.0], [1.0, 1.0]], "y": ["a", "b"]}


def test_roundtrip_and_cache(ms):
    ms.save_model(_model())
    m1 = ms.load_model()
    assert set(m1["groups"]) == {"a", "b"}
    assert ms.load_model() is m1  # cached, not reloaded


def test_corrupt_file_returns_none(ms):
    open(ms.MODEL_PATH, "wb").write(b"garbage")
    assert ms.load_model() is None


def test_missing_file_returns_none(ms):
    assert ms.load_model() is None


def test_training_lock_is_exclusive(ms):
    with ms.training_lock(timeout=0) as a:
        assert a is True
        with ms.training_lock(timeout=0) as b:
            assert b is False
        result = []
        t = threading.Thread(
            target=lambda: result.append(ms.training_lock(timeout=0).__enter__()))
        t.start(); t.join()
        assert result == [False]
    with ms.training_lock(timeout=0) as c:
        assert c is True


def test_readers_never_see_partial_file(ms):
    ms.save_model(_model())
    stop, errors = threading.Event(), []

    def writer():
        while not stop.is_set():
            ms.save_model(_model())

    t = threading.Thread(target=writer); t.start()
    try:
        for _ in range(200):
            m = ms.load_model()
            if m is None:
                errors.append("unreadable")
    finally:
        stop.set(); t.join()
    assert not errors


@pytest.fixture
def eq(monkeypatch):
    fake = types.ModuleType("src.database.config")
    fake.supabase = MagicMock()
    monkeypatch.setitem(sys.modules, "src.database.config", fake)
    sys.modules.pop("src.services.email_queue", None)
    from src.services import email_queue
    monkeypatch.setattr(email_queue, "SEND_DELAY", 0)
    monkeypatch.setattr(email_queue, "_reserve_quota", lambda n: n)
    monkeypatch.setattr(email_queue.es, "smtp_open", lambda: None)
    monkeypatch.setattr(email_queue.es, "smtp_close", lambda: None)
    monkeypatch.setattr(email_queue.es, "send_teacher_summary_email", lambda *a, **k: None)
    return email_queue


def _data(n, missing_email=()):
    students = [{"student_id": i, "name": f"S{i}",
                 "email": None if i in missing_email else f"s{i}@x.com"} for i in range(n)]
    logs = [{"student_id": i, "subject_id": 1, "timestamp": "t", "is_present": True}
            for i in range(n)]
    return logs, students


def test_classify(eq):
    c = eq.classify_smtp_error
    assert c(smtplib.SMTPAuthenticationError(535, b"bad")) == "blocked"
    assert c(smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded")) == "blocked"
    assert c(smtplib.SMTPDataError(421, b"try later")) == "blocked"
    assert c(smtplib.SMTPServerDisconnected()) == "retry"
    assert c(smtplib.SMTPRecipientsRefused({})) == "invalid"
    assert c(ValueError("x")) == "failed"


def test_blocked_batch_defers_rest_and_is_not_reported_as_missing_email(eq, monkeypatch):
    calls = {"n": 0}

    def send(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded")

    monkeypatch.setattr(eq.es, "send_student_attendance_email", send)
    logs, students = _data(5)
    job = eq._build_job(logs, "Math", "M1", "T", "", "t", students)
    eq._run(job)
    assert job["sent"] == 2 and job["deferred"] == 3
    assert job["failed"] == [] and job["no_email"] == []
    assert job["block_reason"]


def test_missing_email_counted_separately(eq, monkeypatch):
    monkeypatch.setattr(eq.es, "send_student_attendance_email", lambda *a, **k: None)
    logs, students = _data(3, missing_email={1})
    job = eq._build_job(logs, "Math", "M1", "T", "t@x.com", "t", students)
    eq._run(job)
    assert job["sent"] == 2 and job["no_email"] == ["S1"]
    assert job["failed"] == [] and job["teacher_status"] == "sent"


def test_quota_limits_sends(eq, monkeypatch):
    monkeypatch.setattr(eq, "_reserve_quota", lambda n: 2)
    monkeypatch.setattr(eq.es, "send_student_attendance_email", lambda *a, **k: None)
    logs, students = _data(5)
    job = eq._build_job(logs, "Math", "M1", "T", "", "t", students)
    eq._run(job)
    assert job["sent"] == 2 and job["deferred"] == 3 and job["block_reason"] == "daily_limit"
