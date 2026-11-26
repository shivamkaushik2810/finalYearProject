from src.services import notification_service as svc

SUB = {"id": 5, "subject_code": "BCS 603", "section_code": "3D", "period_no": 6,
       "substitution_date": "2026-11-25", "room": "B 202", "reasons": None}
T_PS = "aaaaaaaa-0000-0000-0000-000000000002"
T_RM = "aaaaaaaa-0000-0000-0000-000000000001"


def test_assignment_queues_one_notice_per_recipient(fake_db):
    fake_db.rpcs["notification_enqueue"] = lambda p: True
    n = svc.notify_assignment(SUB, T_PS, "ps@example.com", T_RM, "rm@example.com", "Nikhil Tomar")
    assert n == 2
    names = [name for name, _ in fake_db.rpc_calls]
    assert names == ["notification_enqueue", "notification_enqueue"]


def test_a_duplicate_is_reported_as_not_queued(fake_db):
    fake_db.rpcs["notification_enqueue"] = lambda p: False
    assert svc.notify_assignment(SUB, T_PS, "ps@example.com", T_RM, "rm@example.com", "x") == 0


def test_each_recipient_gets_a_different_key(fake_db):
    fake_db.rpcs["notification_enqueue"] = lambda p: True
    svc.notify_assignment(SUB, T_PS, "ps@example.com", T_RM, "rm@example.com", "x")
    keys = [p["p_key"] for _, p in fake_db.rpc_calls]
    assert len(set(keys)) == 2


def test_deliver_marks_missing_address_as_failed_not_sent(fake_db, monkeypatch):
    fake_db.rpcs["notification_claim"] = lambda p: [{"id": 1, "recipient_email": None,
                                                      "subject": "s", "body": "b"}]
    fake_db.rpcs["notification_mark"] = lambda p: None

    class FakeServer:
        def sendmail(self, *a): raise AssertionError("must not send")
        def quit(self): pass
    monkeypatch.setattr(svc, "open_smtp", lambda: (FakeServer(), {"sender": "x@y.z"}))
    out = svc.deliver_due()
    assert out == {"claimed": 1, "sent": 0, "failed": 1}
    marks = [p for n, p in fake_db.rpc_calls if n == "notification_mark"]
    assert marks[0]["p_ok"] is False and "no email" in marks[0]["p_error"]


def test_deliver_sends_once_and_marks_sent(fake_db, monkeypatch):
    fake_db.rpcs["notification_claim"] = lambda p: [{"id": 7, "recipient_email": "ps@example.com",
                                                      "subject": "s", "body": "b"}]
    fake_db.rpcs["notification_mark"] = lambda p: None
    sent = []

    class FakeServer:
        def sendmail(self, sender, to, body): sent.append(to)
        def quit(self): pass
    monkeypatch.setattr(svc, "open_smtp", lambda: (FakeServer(), {"sender": "x@y.z"}))
    out = svc.deliver_due()
    assert out == {"claimed": 1, "sent": 1, "failed": 0}
    assert sent == ["ps@example.com"]


def test_smtp_failure_is_marked_for_retry_not_lost(fake_db, monkeypatch):
    fake_db.rpcs["notification_claim"] = lambda p: [{"id": 9, "recipient_email": "ps@example.com",
                                                      "subject": "s", "body": "b"}]
    fake_db.rpcs["notification_mark"] = lambda p: None

    class FakeServer:
        def sendmail(self, *a): raise OSError("timeout")
        def quit(self): pass
    monkeypatch.setattr(svc, "open_smtp", lambda: (FakeServer(), {"sender": "x@y.z"}))
    out = svc.deliver_due()
    assert out["failed"] == 1 and out["sent"] == 0
    marks = [p for n, p in fake_db.rpc_calls if n == "notification_mark"]
    assert marks[0]["p_ok"] is False and marks[0]["p_error"] == "OSError"


def test_nothing_due_does_nothing(fake_db):
    fake_db.rpcs["notification_claim"] = lambda p: []
    assert svc.deliver_due() == {"claimed": 0, "sent": 0, "failed": 0}
