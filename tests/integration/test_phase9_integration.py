"""Phase 9 integration tests against the project's own database.

Safety, in order:
  1. Skipped unless SNAPCLASS_TEST_RUN_ID starts with 'p9-' AND the sender is paused.
  2. Every row written carries the run ID, so cleanup removes only those rows.
  3. Test teachers have no email address, so no mail can be sent.
  4. The app's own config is never imported.
"""
import os
import threading
import uuid

import pytest

RUN = os.environ.get("SNAPCLASS_TEST_RUN_ID", "")
URL = os.environ.get("SNAPCLASS_TEST_URL", "")
SERVICE = os.environ.get("SNAPCLASS_TEST_SERVICE_KEY", "")
ANON = os.environ.get("SNAPCLASS_TEST_ANON_KEY", "")
PAUSED = os.environ.get("SNAPCLASS_SENDER_PAUSED") == "1"


def _skip_reason():
    if not RUN.startswith("p9-"):
        return "set SNAPCLASS_TEST_RUN_ID to a value starting with p9-"
    if not PAUSED:
        return "pause the scheduled sender and set SNAPCLASS_SENDER_PAUSED=1"
    if not (URL and SERVICE and ANON):
        return "set SNAPCLASS_TEST_URL, SNAPCLASS_TEST_SERVICE_KEY and SNAPCLASS_TEST_ANON_KEY"
    return None


_reason = _skip_reason()
pytestmark = pytest.mark.skipif(_reason is not None, reason=_reason or "")


def _client(key):
    from supabase import create_client
    return create_client(URL, key)


def _svc():
    return _client(SERVICE)


def _anon():
    return _client(ANON)


def _race(n, fn):
    out, lock = [], threading.Lock()

    def run():
        try:
            result = ("ok", fn())
        except Exception as exc:
            result = ("err", str(exc))
        with lock:
            out.append(result)
    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def _is_denied(exc):
    text = str(exc).lower()
    return "permission denied" in text or "42501" in text


@pytest.fixture
def world():
    s = _svc()
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    teacher = s.table("teachers").insert({
        "username": tag, "name": f"Phase9 {tag}", "password": "x",
        "email": None, "status": "approved"}).execute().data[0]
    version = s.table("timetable_versions").insert({
        "label": tag, "status": "draft", "created_by": tag}).execute().data[0]
    sub = s.table("faculty_substitutions").insert({
        "version_id": version["id"], "substitution_date": "2026-11-25", "weekday": 3, "period_no": 6,
        "section_code": "3C", "subject_code": "PH9", "original_teacher_code": "ZZ",
        "substitute_teacher_id": teacher["teacher_id"], "status": "proposed",
        "created_by": tag}).execute().data[0]
    return {"tag": tag, "teacher": teacher["teacher_id"], "version": version["id"], "sub": sub["id"]}


def _enqueue(tag, i):
    return _svc().rpc("notification_enqueue", {
        "p_key": f"{tag}-{i}", "p_kind": "admin", "p_teacher_id": None,
        "p_email": "", "p_subject": f"{tag} {i}", "p_body": "test"}).execute().data


def _claim(limit):
    return _svc().rpc("notification_claim", {"p_limit": limit}).execute().data or []


ANON_CALLS = [
    ("faculty_substitution_confirm", {"p_id": 1, "p_actor": "x"}),
    ("faculty_substitution_reject", {"p_id": 1, "p_actor": "x"}),
    ("faculty_substitution_override", {"p_id": 1, "p_teacher_id": "00000000-0000-0000-0000-000000000000",
                                       "p_reason": "x", "p_actor": "x"}),
    ("faculty_substitution_save_plan", {"p_version_id": 1, "p_date": "2026-11-25", "p_rows": [],
                                        "p_actor": "x"}),
    ("notification_claim", {"p_limit": 1}),
    ("notification_enqueue", {"p_key": "x", "p_kind": "admin", "p_teacher_id": None,
                              "p_email": "", "p_subject": "x", "p_body": "x"}),
]


@pytest.mark.parametrize("name,params", ANON_CALLS)
def test_anonymous_key_cannot_call_substitution_functions(name, params):
    with pytest.raises(Exception) as info:
        _anon().rpc(name, params).execute()
    assert _is_denied(info.value), f"{name} was not refused: {info.value}"


@pytest.mark.parametrize("table", [
    "faculty_substitutions", "faculty_substitution_events", "substitution_exclusions",
    "notification_outbox", "notification_inbox", "faculty_absences", "faculty_absence_log"])
def test_anonymous_key_cannot_read_planning_tables(table):
    try:
        data = _anon().table(table).select("*").limit(1).execute().data
    except Exception as exc:
        assert _is_denied(exc), f"{table}: unexpected error {exc}"
        return
    assert data == [], f"{table} is readable with the public key"


def test_only_one_of_many_concurrent_confirms_succeeds(world):
    def confirm():
        return _svc().rpc("faculty_substitution_confirm",
                          {"p_id": world["sub"], "p_actor": world["tag"]}).execute().data
    results = _race(8, confirm)
    assert sum(1 for status, _ in results if status == "ok") == 1, results


def test_concurrent_plans_leave_one_proposal_per_slot(world):
    row = {"weekday": 3, "period": 6, "section_code": "3C", "subject_code": "PH9", "room": "SAMPLE",
           "absent_code": "ZZ", "substitute_teacher_id": world["teacher"], "status": "proposed",
           "score": 50, "factors": {}, "alternatives": [], "reasons": None}

    def save():
        return _svc().rpc("faculty_substitution_save_plan", {
            "p_version_id": world["version"], "p_date": "2026-11-25",
            "p_rows": [row], "p_actor": world["tag"]}).execute().data
    results = _race(6, save)
    assert all(status == "ok" for status, _ in results), results
    left = (_svc().table("faculty_substitutions").select("id")
            .eq("version_id", world["version"]).eq("period_no", 6).eq("status", "proposed")
            .execute().data)
    assert len(left) == 1


def test_duplicate_notice_key_is_stored_once():
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    assert _enqueue(tag, 0) is True
    assert _enqueue(tag, 0) is False


def test_each_notice_is_claimed_once_under_concurrency():
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    for i in range(20):
        _enqueue(tag, i)
    claimed, lock = [], threading.Lock()

    def worker():
        while True:
            rows = _claim(3)
            if not rows:
                return
            with lock:
                claimed.extend(r["id"] for r in rows if r["idempotency_key"].startswith(tag))
    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 20, f"claimed {len(claimed)} of 20"
    assert len(set(claimed)) == 20, "a notice was claimed by two workers"


def test_claimed_notice_is_leased_not_reclaimed_immediately():
    tag = RUN + "-" + uuid.uuid4().hex[:6]
    _enqueue(tag, 0)
    ours = None
    for _ in range(50):
        rows = _claim(1000)
        if not rows:
            break
        for r in rows:
            if r["idempotency_key"].startswith(tag):
                ours = r["id"]
        if ours is not None:
            break
    assert ours is not None, "notice was never claimed"
    again = _claim(1000)
    assert all(r["id"] != ours for r in again), "claimed notice was handed out again before its lease ended"
