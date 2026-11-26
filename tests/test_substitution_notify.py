from src.services import substitution_notify as sn


def test_notify_assigned_never_raises_on_database_error(monkeypatch):
    def boom(_):
        raise RuntimeError("db down")
    monkeypatch.setattr(sn, "_sub", boom)
    warning = sn.notify_assigned(1)
    assert warning and "could not be queued" in warning


def test_notify_unassigned_never_raises_on_database_error(monkeypatch):
    def boom(_):
        raise RuntimeError("db down")
    monkeypatch.setattr(sn, "_sub", boom)
    assert "could not be queued" in sn.notify_unassigned(1)


def test_missing_substitution_is_a_no_op(monkeypatch):
    monkeypatch.setattr(sn, "_sub", lambda _: None)
    assert sn.notify_assigned(1) is None
    assert sn.notify_unassigned(1) is None
