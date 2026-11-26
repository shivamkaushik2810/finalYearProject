"""Phase 9 claim tests. Run only through the safety gates in test_phase9_integration.
Test notices use a reserved .invalid address, so no real mailbox can receive them.
Every loop is bounded, so a fault fails the test instead of hanging."""
import threading
import uuid

from tests.integration.test_phase9_integration import RUN, _claim, _svc  # noqa: F401
from tests.integration.test_phase9_integration import pytestmark  # noqa: F401

TEST_ADDRESS = "phase9@example.invalid"
MAX_ROUNDS = 40
JOIN_SECONDS = 60


def _enqueue_pending(tag, i):
    return _svc().rpc("notification_enqueue", {
        "p_key": f"{tag}-{i}", "p_kind": "admin", "p_teacher_id": None,
        "p_email": TEST_ADDRESS, "p_subject": f"{tag} {i}", "p_body": "test"}).execute().data


def test_each_notice_is_claimed_once_under_concurrency():
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    for i in range(20):
        _enqueue_pending(tag, i)
    claimed, lock = [], threading.Lock()

    def worker():
        for _ in range(MAX_ROUNDS):
            rows = _claim(3)
            if not rows:
                return
            with lock:
                claimed.extend(r["id"] for r in rows if r["idempotency_key"].startswith(tag))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_SECONDS)
    assert not any(t.is_alive() for t in threads), "a worker did not finish in time"
    assert len(claimed) == 20, f"claimed {len(claimed)} of 20"
    assert len(set(claimed)) == 20, "a notice was claimed by two workers"


def test_claimed_notice_is_leased_not_reclaimed_immediately():
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    _enqueue_pending(tag, 0)
    ours = None
    for _ in range(MAX_ROUNDS):
        rows = _claim(50)
        if not rows:
            break
        mine = [r["id"] for r in rows if r["idempotency_key"].startswith(tag)]
        if mine:
            ours = mine[0]
            break
    assert ours is not None, "notice was never claimed"
    again = _claim(50)
    assert all(r["id"] != ours for r in again), "claimed notice was handed out again before its lease ended"
