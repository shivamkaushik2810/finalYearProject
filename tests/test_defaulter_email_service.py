import email
from src.services import defaulter_email_service as svc


class FakeSMTP:
    sent = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def ehlo(self): pass
    def starttls(self): pass
    def login(self, *a): pass
    def sendmail(self, frm, to, msg): FakeSMTP.sent.append((to, msg))


def _body(monkeypatch, student, parent, subj):
    monkeypatch.setattr(svc.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(svc, "_get_config", lambda: {"sender_email": "a@b.c", "sender_password": "x"})
    FakeSMTP.sent.clear()
    svc.send_defaulter_report(
        "p@example.com", parent, student, 40.0,
        [{"subject": subj, "attended": 4, "total": 10, "pct": 40.0}],
        [("1 Oct", subj, "Absent")], [], None)
    m = email.message_from_string(FakeSMTP.sent[0][1])
    part = [p for p in m.walk() if p.get_content_type() == "text/html"][0]
    return part.get_payload(decode=True).decode("utf-8")


def test_html_is_escaped(monkeypatch):
    st = {"name": "<script>alert(1)</script>", "roll_no": "1", "section": "A", "course": "B.Tech", "year": "4"}
    body = _body(monkeypatch, st, "<b>P</b>", "<i>CS</i>")
    assert "<script>" not in body and "&lt;script&gt;" in body
    assert "<b>P</b>" not in body and "<i>CS</i>" not in body


def test_missing_optional_fields(monkeypatch):
    body = _body(monkeypatch, {"name": "X"}, None, "CS")
    assert "Parent" in body and "N/A" in body
