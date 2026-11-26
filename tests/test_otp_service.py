"""Tests for src/services/otp_service.py.

Runs against tests/fake_supabase.py via the shared conftest fixture. The fake does
not assign row ids, so rows that verify_otp must update are seeded with an explicit
id (the real table assigns one). Email sending is replaced by a capture function.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.services import otp_service as otp

EMAIL = "parent@example.com"
PURPOSE = "parent_login"


def _seed(fake_db, code, *, attempts=0, created_at=None, verified=False,
          email=EMAIL, purpose=PURPOSE, row_id=1):
    fake_db.tables.setdefault("otp_verifications", []).append({
        "id": row_id,
        "email": email,
        "purpose": purpose,
        "otp": otp._hash_otp(email, code, purpose),
        "is_verified": verified,
        "attempts": attempts,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    })


def _rows(fake_db):
    return fake_db.tables.get("otp_verifications", [])


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(otp, "_send", lambda to, subj, html, plain: sent.append((to, subj, html, plain)))
    return sent


# ── generation and hashing ──────────────────────────────────────────

def test_generate_otp_default_is_six_digits():
    for _ in range(200):
        code = otp.generate_otp()
        assert len(code) == 6 and code.isdigit()


def test_generate_otp_respects_length():
    assert len(otp.generate_otp(8)) == 8


def test_hash_ignores_email_case():
    assert otp._hash_otp("A@X.com", "123456", PURPOSE) == otp._hash_otp("a@x.com", "123456", PURPOSE)


def test_hash_is_bound_to_purpose():
    assert otp._hash_otp(EMAIL, "123456", "parent_email") != otp._hash_otp(EMAIL, "123456", "student_email")


def test_hash_differs_for_different_codes():
    assert otp._hash_otp(EMAIL, "123456", PURPOSE) != otp._hash_otp(EMAIL, "654321", PURPOSE)


# ── save_otp ────────────────────────────────────────────────────────

def test_save_stores_hash_never_plaintext(fake_db):
    otp.save_otp(EMAIL, "123456", PURPOSE)
    rows = _rows(fake_db)
    assert len(rows) == 1
    assert rows[0]["otp"] != "123456"
    assert rows[0]["otp"] == otp._hash_otp(EMAIL, "123456", PURPOSE)
    assert rows[0]["is_verified"] is False and rows[0]["attempts"] == 0


def test_save_replaces_previous_otp_for_same_email_and_purpose_only(fake_db):
    _seed(fake_db, "111111", row_id=1)
    _seed(fake_db, "222222", purpose="student_email", row_id=2)
    otp.save_otp(EMAIL, "333333", PURPOSE)
    same = [r for r in _rows(fake_db) if r["email"] == EMAIL and r["purpose"] == PURPOSE]
    other = [r for r in _rows(fake_db) if r["purpose"] == "student_email"]
    assert len(same) == 1 and same[0]["otp"] == otp._hash_otp(EMAIL, "333333", PURPOSE)
    assert len(other) == 1, "a different purpose must not be deleted"


# ── verify_otp ──────────────────────────────────────────────────────

def test_verify_correct_code_marks_verified(fake_db):
    _seed(fake_db, "123456")
    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is True and "verified" in msg.lower()
    assert _rows(fake_db)[0]["is_verified"] is True


def test_verify_strips_whitespace(fake_db):
    _seed(fake_db, "123456")
    assert otp.verify_otp(EMAIL, "  123456 ", PURPOSE)[0] is True


def test_verify_wrong_code_counts_attempt_and_reports_left(fake_db):
    _seed(fake_db, "123456")
    ok, msg = otp.verify_otp(EMAIL, "000000", PURPOSE)
    assert ok is False and "4 attempt(s) left" in msg
    assert _rows(fake_db)[0]["attempts"] == 1
    assert _rows(fake_db)[0]["is_verified"] is False


def test_verify_without_request_says_send_first(fake_db):
    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is False and "not found" in msg.lower()


def test_verify_is_single_use(fake_db):
    _seed(fake_db, "123456")
    assert otp.verify_otp(EMAIL, "123456", PURPOSE)[0] is True
    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is False and "not found" in msg.lower()


def test_verify_rejects_expired_code_and_deletes_it(fake_db):
    old = (datetime.now(timezone.utc) - timedelta(minutes=otp.OTP_TTL.seconds // 60 + 1)).isoformat()
    _seed(fake_db, "123456", created_at=old)
    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is False and "expired" in msg.lower()
    assert _rows(fake_db) == []


def test_verify_accepts_code_just_inside_ttl(fake_db):
    recent = (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat()
    _seed(fake_db, "123456", created_at=recent)
    assert otp.verify_otp(EMAIL, "123456", PURPOSE)[0] is True


def test_lockout_after_max_wrong_attempts_even_with_correct_code(fake_db):
    _seed(fake_db, "123456")
    lefts = []
    for _ in range(otp.MAX_ATTEMPTS):
        ok, msg = otp.verify_otp(EMAIL, "000000", PURPOSE)
        assert ok is False
        lefts.append(msg)
    assert lefts[0].endswith("4 attempt(s) left.") and lefts[-1].endswith("0 attempt(s) left.")

    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is False and "too many" in msg.lower()
    assert _rows(fake_db) == [], "locked-out OTP must be deleted"


def test_database_error_fails_closed(fake_db):
    _seed(fake_db, "123456")
    fake_db.fail_tables.add("otp_verifications")
    ok, msg = otp.verify_otp(EMAIL, "123456", PURPOSE)
    assert ok is False and msg.startswith("Verification failed")


# ── send_otp_email / send_and_save_otp ──────────────────────────────

def test_send_email_contains_code_and_escapes_name(captured):
    otp.send_otp_email(EMAIL, "654321", PURPOSE, "<script>x</script>")
    to, subj, html, plain = captured[0]
    assert to == EMAIL and "654321" in subj
    assert "654321" in plain and "654321" in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_send_and_save_stores_hash_and_mails_code(fake_db, captured, monkeypatch):
    monkeypatch.setattr(otp, "generate_otp", lambda length=6: "123456")
    assert otp.send_and_save_otp(EMAIL, PURPOSE, "Ravi") is True
    assert _rows(fake_db)[0]["otp"] == otp._hash_otp(EMAIL, "123456", PURPOSE)
    assert "123456" in captured[0][1]


def test_resend_within_cooldown_is_refused_and_not_sent(fake_db, captured):
    _seed(fake_db, "111111")  # created just now
    with pytest.raises(ValueError, match="30 seconds"):
        otp.send_and_save_otp(EMAIL, PURPOSE)
    assert captured == []


def test_resend_after_cooldown_is_allowed(fake_db, captured, monkeypatch):
    monkeypatch.setattr(otp, "generate_otp", lambda length=6: "222222")
    old = (datetime.now(timezone.utc) - timedelta(seconds=otp.RESEND_COOLDOWN.seconds + 1)).isoformat()
    _seed(fake_db, "111111", created_at=old)
    assert otp.send_and_save_otp(EMAIL, PURPOSE) is True
    assert len(captured) == 1
