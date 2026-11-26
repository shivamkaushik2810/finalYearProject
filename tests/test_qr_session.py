"""Tests for src/components/qr_session.py (token maths, session lifecycle,
scan validation and teacher confirmation).

Limits of the fake database, so these are NOT covered here:
- It does not enforce unique indexes. Duplicate-scan behaviour is simulated by
  wrapping record_scan with a check on (session, student, method).
- It has no upsert/storage. Not used by the functions tested here.
- It compares values by exact type, so IDs are kept consistent per test.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.components import qr_session as qs

SUBJECT = 10
TEACHER = 7
STUDENT = 5
SESSION_ID = 1
CODE = "K7M2QX"
FIXED_SLOT = 1_000_000


def _iso(delta_min):
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


def _session(**over):
    row = {
        "id": SESSION_ID, "subject_id": SUBJECT, "teacher_id": TEACHER,
        "session_code": CODE, "is_active": True,
        "expires_at": _iso(5), "session_ts": "2026-11-23T10:00:00",
    }
    row.update(over)
    return row


@pytest.fixture
def fixed_slot(monkeypatch):
    monkeypatch.setattr(qs, "_slot", lambda now=None: FIXED_SLOT)


@pytest.fixture
def live(fake_db, fixed_slot):
    fake_db.tables["attendance_sessions"] = [_session()]
    fake_db.tables["subject_students"] = [{"student_id": STUDENT, "subject_id": SUBJECT}]
    fake_db.tables["subjects"] = [{"subject_id": SUBJECT, "name": "Maths", "teacher_id": TEACHER}]
    return fake_db


def _current_token(session=None):
    return qs._token(session or _session(), FIXED_SLOT)


# ── token maths ─────────────────────────────────────────────────────

def test_token_has_six_chars_from_alphabet():
    tok = qs._token(_session(), FIXED_SLOT)
    assert len(tok) == qs.CODE_LEN and set(tok) <= set(qs.ALPHABET)


def test_token_is_deterministic():
    assert qs._token(_session(), 5) == qs._token(_session(), 5)


def test_token_changes_with_slot():
    tokens = {qs._token(_session(), s) for s in range(20)}
    assert len(tokens) > 1


def test_token_changes_with_session_code():
    assert qs._token(_session(), 5) != qs._token(_session(session_code="ZZZZZZ"), 5)


def test_slot_advances_every_rotate_period():
    base = datetime(2026, 11, 23, 10, 0, 0, tzinfo=timezone.utc)
    assert qs._slot(base + timedelta(seconds=qs.ROTATE_SECONDS)) == qs._slot(base) + 1


def test_valid_tokens_accept_current_and_previous_slot_only(fixed_slot):
    s = _session()
    valid = qs._valid_tokens(s)
    assert qs._token(s, FIXED_SLOT) in valid
    assert qs._token(s, FIXED_SLOT - 1) in valid  # grace slot
    assert qs._token(s, FIXED_SLOT - 2) not in valid


# ── helpers ─────────────────────────────────────────────────────────

def test_is_expired_future_past_and_malformed():
    assert qs._is_expired(_session(expires_at=_iso(5))) is False
    assert qs._is_expired(_session(expires_at=_iso(-1))) is True
    assert qs._is_expired(_session(expires_at="not a date")) is True, "fail closed"
    assert qs._is_expired({"id": 1}) is True, "missing expiry must fail closed"


def test_session_id_of_prefers_id_then_session_id():
    assert qs.session_id_of({"id": 3}) == 3
    assert qs.session_id_of({"session_id": 4}) == 4
    assert qs.session_id_of({"id": None, "session_id": 4}) == 4


@pytest.mark.parametrize("raw, expected", [
    ("https://snapclass-main.streamlit.app/?qr-code=k7m2qx", "K7M2QX"),
    ("K7M2QX", "K7M2QX"),
    ("k7m2qx", "K7M2QX"),
    ("  K7M2QX  ", "K7M2QX"),
    ("K7M2Q", None),
    ("K7M2QX!", None),
    ("", None),
    (None, None),
])
def test_extract_code(raw, expected):
    assert qs._extract_code(raw) == expected


def test_qr_png_is_png_bytes():
    assert qs._qr_png("https://example.com/?qr-code=ABCDEF").startswith(b"\x89PNG")


# ── mark_attendance (student scan) ──────────────────────────────────

def test_valid_scan_records_pending_qr_attendance(live):
    ok, msg = qs.mark_attendance(STUDENT, _current_token())
    assert ok is True and "Maths" in msg
    scans = live.tables["attendance_scans"]
    assert len(scans) == 1
    assert scans[0]["student_id"] == STUDENT and scans[0]["method"] == "qr"
    assert scans[0]["session_id"] == SESSION_ID


def test_lowercase_and_padded_code_accepted(live):
    assert qs.mark_attendance(STUDENT, "  " + _current_token().lower() + " ")[0] is True


def test_wrong_length_rejected_without_writing(live):
    ok, msg = qs.mark_attendance(STUDENT, "ABC")
    assert ok is False and "6-character" in msg
    assert live.tables.get("attendance_scans", []) == []


def test_unknown_code_rejected(live):
    tok = _current_token()
    bad = ("A" if tok[0] != "A" else "B") + tok[1:]
    assert bad not in qs._valid_tokens(_session())
    ok, msg = qs.mark_attendance(STUDENT, bad)
    assert ok is False and "Invalid or expired" in msg
    assert live.tables.get("attendance_scans", []) == []


def test_expired_session_rejected_even_with_valid_token(live):
    live.tables["attendance_sessions"] = [_session(expires_at=_iso(-1))]
    ok, msg = qs.mark_attendance(STUDENT, _current_token())
    assert ok is False and "expired" in msg.lower()
    assert live.tables.get("attendance_scans", []) == []


def test_student_not_enrolled_rejected_without_writing(live):
    live.tables["subject_students"] = []
    ok, msg = qs.mark_attendance(STUDENT, _current_token())
    assert ok is False and "not enrolled" in msg.lower()
    assert live.tables.get("attendance_scans", []) == []


def test_duplicate_scan_same_method_rejected(live, monkeypatch):
    """Simulates the unique index on (session, student, method)."""
    real_record = qs.record_scan

    def unique_record(session_id, student_id, subject_id, method):
        existing = [r for r in live.tables.get("attendance_scans", [])
                    if (r["session_id"], r["student_id"], r["method"]) == (session_id, student_id, method)]
        if existing:
            return False, "already recorded with this method"
        return real_record(session_id, student_id, subject_id, method)

    monkeypatch.setattr(qs, "record_scan", unique_record)
    tok = _current_token()
    assert qs.mark_attendance(STUDENT, tok)[0] is True
    ok, msg = qs.mark_attendance(STUDENT, tok)
    assert ok is False and "already marked" in msg
    assert len(live.tables["attendance_scans"]) == 1


def test_scan_after_stop_now_is_rejected(live):
    s = qs._get_active(SUBJECT)
    qs._stop_now(s)
    ok, msg = qs.mark_attendance(STUDENT, _current_token())
    assert ok is False and "expired" in msg.lower()


# ── session lifecycle ───────────────────────────────────────────────

def test_start_session_creates_active_five_minute_session(fake_db, fixed_slot):
    fake_db.tables["attendance_sessions"] = []
    row = qs._start_session(SUBJECT, TEACHER, 5)
    assert row["is_active"] is True
    assert row["subject_id"] == SUBJECT and row["teacher_id"] == TEACHER
    assert len(row["session_code"]) == qs.CODE_LEN
    assert set(row["session_code"]) <= set(qs.ALPHABET)
    remaining = datetime.fromisoformat(row["expires_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=4) < remaining <= timedelta(minutes=5, seconds=5)


def test_new_code_gives_up_after_repeated_clashes(fake_db, monkeypatch):
    fake_db.tables["attendance_sessions"] = [_session(session_code="AAAAAA")]
    monkeypatch.setattr(qs.secrets, "choice", lambda seq: "A")  # every candidate is AAAAAA
    with pytest.raises(RuntimeError, match="unique code"):
        qs._new_code()


def test_get_active_returns_only_active_session(fake_db):
    fake_db.tables["attendance_sessions"] = [
        _session(id=1, is_active=False),
        _session(id=2, is_active=True),
    ]
    assert qs._get_active(SUBJECT)["id"] == 2


def test_get_active_none_when_no_session(fake_db):
    fake_db.tables["attendance_sessions"] = []
    assert qs._get_active(SUBJECT) is None


def test_stop_now_ends_window_immediately(live):
    s = qs._get_active(SUBJECT)
    qs._stop_now(s)
    updated = qs._get_active(SUBJECT)
    assert updated is not None and qs._is_expired(updated) is True


def test_close_deactivates_session(live):
    qs._close(_session())
    assert qs._get_active(SUBJECT) is None


def test_discard_removes_scans_and_closes(live, monkeypatch):
    monkeypatch.setattr(qs, "st", SimpleNamespace(session_state={}))
    live.tables["attendance_scans"] = [{"session_id": SESSION_ID, "student_id": STUDENT, "method": "qr"}]
    qs._discard_session(_session())
    assert live.tables["attendance_scans"] == []
    assert qs._get_active(SUBJECT) is None


# ── teacher confirmation ────────────────────────────────────────────

@pytest.fixture
def confirm_env(live, monkeypatch):
    monkeypatch.setattr(qs, "st", SimpleNamespace(session_state={}))
    live.tables["subject_students"] = [
        {"student_id": STUDENT, "subject_id": SUBJECT},
        {"student_id": 6, "subject_id": SUBJECT},
    ]
    return live


def test_confirm_rejects_other_teachers_session(confirm_env):
    with pytest.raises(PermissionError):
        qs._confirm_session(_session(), SUBJECT, 8, {STUDENT}, {})


def test_confirm_writes_every_enrolled_student(confirm_env):
    logs = qs._confirm_session(_session(), SUBJECT, TEACHER, {STUDENT}, {STUDENT: {"nfc", "qr"}})
    assert len(logs) == 2
    rows = {r["student_id"]: r for r in confirm_env.tables["attendance_logs"]}
    assert rows[STUDENT]["is_present"] is True
    assert rows[STUDENT]["method"] == "qr+nfc"          # fixed method order
    assert rows[6]["is_present"] is False and rows[6]["method"] is None
    assert rows[STUDENT]["session_id"] == SESSION_ID
    assert rows[STUDENT]["timestamp"] == "2026-11-23T10:00:00"


def test_confirm_marks_hand_ticked_student_as_manual(confirm_env):
    qs._confirm_session(_session(), SUBJECT, TEACHER, {6}, {})
    rows = {r["student_id"]: r for r in confirm_env.tables["attendance_logs"]}
    assert rows[6]["is_present"] is True and rows[6]["method"] == "manual"


def test_confirm_closes_session(confirm_env):
    qs._confirm_session(_session(), SUBJECT, TEACHER, {STUDENT}, {})
    assert qs._get_active(SUBJECT) is None


def test_confirm_twice_is_refused_and_writes_nothing_more(confirm_env):
    qs._confirm_session(_session(), SUBJECT, TEACHER, {STUDENT}, {})
    count = len(confirm_env.tables["attendance_logs"])
    with pytest.raises(RuntimeError, match="already saved"):
        qs._confirm_session(_session(), SUBJECT, TEACHER, {STUDENT}, {})
    assert len(confirm_env.tables["attendance_logs"]) == count
