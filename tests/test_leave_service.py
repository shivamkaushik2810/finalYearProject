"""Tests for src/services/leave_service.py.

Notes on the fake database:
- Leave-related IDs are strings. The leave_requests IDs are text columns per
  sql/05_fixes.sql, and the fake compares values by exact type.
- Teacher IDs are ints, matching subjects.teacher_id in the fake.
- Storage (certificate download and the signed-URL path) is not implemented in the
  fake. The upload-failure path is tested because it must return False rather than
  record a leave. The owner's signed-URL path is NOT covered here.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from src.services import leave_service as ls

TODAY = date.today()
STUDENT = "5"
OTHER_STUDENT = "6"
SUBJ = "10"          # owned by teacher 7
SUBJ_OTHER = "11"    # owned by teacher 8
TEACHER = 7
OTHER_TEACHER = 8
VALID_PDF = b"%PDF-1.4 minimal"


@pytest.fixture
def base(fake_db):
    fake_db.tables["subjects"] = [
        {"subject_id": SUBJ, "teacher_id": TEACHER, "name": "Maths", "subject_code": "M1"},
        {"subject_id": SUBJ_OTHER, "teacher_id": OTHER_TEACHER, "name": "Physics", "subject_code": "P1"},
    ]
    fake_db.tables["subject_students"] = [{"student_id": STUDENT, "subject_id": SUBJ}]
    fake_db.tables["students"] = [{"student_id": STUDENT, "name": "Aarav", "roll_no": "A01", "section": "A"}]
    fake_db.tables["leave_requests"] = []
    fake_db.tables["attendance_logs"] = []
    return fake_db


def _leave(leave_id="L1", student=STUDENT, subject=SUBJ, start=None, end=None,
           status="pending", kind="leave", reason="fever and rest", document_path=None):
    start = start or TODAY + timedelta(days=2)
    end = end or TODAY + timedelta(days=3)
    return {
        "id": leave_id, "student_id": student, "subject_id": subject, "kind": kind,
        "start_date": str(start), "end_date": str(end), "reason": reason,
        "status": status, "created_at": datetime.now(timezone.utc).isoformat(),
        "document_path": document_path,
    }


# ── submit_leave: validation ────────────────────────────────────────

def test_short_reason_rejected(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY, TODAY, "no")
    assert ok is False and "5-500" in msg
    assert base.tables["leave_requests"] == []


def test_end_before_start_rejected(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY + timedelta(days=2), TODAY, "fever and rest")
    assert ok is False and "before start" in msg


def test_span_over_thirty_days_rejected(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY, TODAY + timedelta(days=30), "fever and rest")
    assert ok is False and "at most 30 days" in msg


def test_request_older_than_thirty_days_rejected(base):
    old = TODAY - timedelta(days=31)
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "leave", old, old, "fever and rest")
    assert ok is False and "older than 30 days" in msg


def test_unknown_kind_rejected(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "holiday", TODAY, TODAY, "fever and rest")
    assert ok is False and "Invalid request type" in msg


def test_bad_certificate_rejected_before_any_write(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "medical", TODAY, TODAY, "fever and rest",
                              doc_name="note.pdf", doc_bytes=b"MZ not a pdf")
    assert ok is False and "Only genuine PDF" in msg
    assert base.tables["leave_requests"] == []


# ── submit_leave: enrolment and overlap ─────────────────────────────

def test_not_enrolled_student_rejected(base):
    ok, msg = ls.submit_leave(OTHER_STUDENT, SUBJ, "leave", TODAY, TODAY, "fever and rest")
    assert ok is False and "not enrolled" in msg.lower()
    assert base.tables["leave_requests"] == []


def test_overlapping_pending_request_rejected(base):
    base.tables["leave_requests"] = [_leave(start=TODAY + timedelta(days=2), end=TODAY + timedelta(days=3))]
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY + timedelta(days=3), TODAY + timedelta(days=4),
                              "fever and rest")
    assert ok is False and "already have a pending/approved" in msg
    assert len(base.tables["leave_requests"]) == 1


def test_overlapping_approved_request_rejected(base):
    base.tables["leave_requests"] = [_leave(status="approved")]
    ok, _ = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY + timedelta(days=2), TODAY + timedelta(days=2),
                            "fever and rest")
    assert ok is False


def test_rejected_request_does_not_block_new_one(base):
    base.tables["leave_requests"] = [_leave(status="rejected")]
    ok, _ = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY + timedelta(days=2), TODAY + timedelta(days=3),
                            "fever and rest")
    assert ok is True


def test_adjacent_non_overlapping_request_allowed(base):
    base.tables["leave_requests"] = [_leave(start=TODAY + timedelta(days=2), end=TODAY + timedelta(days=3))]
    ok, _ = ls.submit_leave(STUDENT, SUBJ, "leave", TODAY + timedelta(days=4), TODAY + timedelta(days=4),
                            "fever and rest")
    assert ok is True


def test_valid_request_is_stored(base):
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "medical", TODAY + timedelta(days=5), TODAY + timedelta(days=6),
                              "  fever and rest  ")
    assert ok is True and msg == "Request submitted."
    row = base.tables["leave_requests"][0]
    assert row["student_id"] == STUDENT and row["subject_id"] == SUBJ
    assert row["kind"] == "medical"
    assert row["start_date"] == str(TODAY + timedelta(days=5))
    assert row["reason"] == "fever and rest"          # stripped
    assert row["document_path"] is None


def test_certificate_upload_failure_records_nothing(base):
    # The fake has no storage, so the upload raises. The request must not be saved.
    ok, msg = ls.submit_leave(STUDENT, SUBJ, "medical", TODAY + timedelta(days=5), TODAY + timedelta(days=5),
                              "fever and rest", doc_name="note.pdf", doc_bytes=VALID_PDF)
    assert ok is False and "Could not upload" in msg
    assert base.tables["leave_requests"] == []


# ── listing ─────────────────────────────────────────────────────────

def test_list_for_student_returns_only_their_requests_with_subject(base):
    base.tables["leave_requests"] = [_leave("L1", student=STUDENT), _leave("L2", student=OTHER_STUDENT)]
    rows = ls.list_for_student(STUDENT)
    assert [r["id"] for r in rows] == ["L1"]
    assert rows[0]["subjects"]["name"] == "Maths"


def test_list_for_teacher_only_own_subjects_and_status(base):
    base.tables["leave_requests"] = [
        _leave("L1", subject=SUBJ, status="pending"),
        _leave("L2", subject=SUBJ_OTHER, status="pending"),
        _leave("L3", subject=SUBJ, status="approved"),
    ]
    rows = ls.list_for_teacher(TEACHER, "pending")
    assert [r["id"] for r in rows] == ["L1"]
    assert rows[0]["students"]["name"] == "Aarav"


def test_list_for_teacher_with_no_subjects_is_empty(base):
    assert ls.list_for_teacher(99, "pending") == []


# ── review ──────────────────────────────────────────────────────────

def test_review_unknown_request(base):
    assert ls.review_leave("nope", TEACHER, True) == (False, "Request not found.")


def test_review_refuses_already_reviewed(base):
    base.tables["leave_requests"] = [_leave(status="approved")]
    assert ls.review_leave("L1", TEACHER, False)[1] == "Request was already reviewed."


def test_review_refused_for_teacher_who_does_not_own_subject(base):
    base.tables["leave_requests"] = [_leave()]
    ok, msg = ls.review_leave("L1", OTHER_TEACHER, True)
    assert ok is False and "own subjects" in msg
    assert base.tables["leave_requests"][0]["status"] == "pending"


def test_approve_excuses_only_absences_in_range(base):
    base.tables["leave_requests"] = [_leave()]        # covers TODAY+2 .. TODAY+3
    base.tables["attendance_logs"] = [
        {"student_id": STUDENT, "subject_id": SUBJ, "is_present": False,
         "timestamp": f"{TODAY + timedelta(days=2)}T10:00:00"},               # in range, absent
        {"student_id": STUDENT, "subject_id": SUBJ, "is_present": False,
         "timestamp": f"{TODAY + timedelta(days=10)}T10:00:00"},              # outside range
        {"student_id": STUDENT, "subject_id": SUBJ, "is_present": True,
         "timestamp": f"{TODAY + timedelta(days=2)}T11:00:00"},               # in range, present
    ]
    ok, msg = ls.review_leave("L1", TEACHER, True, "ok")
    assert (ok, msg) == (True, "Approved.")
    req = base.tables["leave_requests"][0]
    assert req["status"] == "approved" and req["reviewed_by"] == TEACHER
    in_range, outside, present = base.tables["attendance_logs"]
    assert in_range.get("is_excused") is True
    assert outside.get("is_excused") is not True
    assert present.get("is_excused") is not True


def test_reject_changes_no_attendance(base):
    base.tables["leave_requests"] = [_leave()]
    base.tables["attendance_logs"] = [
        {"student_id": STUDENT, "subject_id": SUBJ, "is_present": False,
         "timestamp": f"{TODAY + timedelta(days=2)}T10:00:00"},
    ]
    assert ls.review_leave("L1", TEACHER, False, "not enough detail") == (True, "Rejected.")
    assert base.tables["leave_requests"][0]["status"] == "rejected"
    assert base.tables["attendance_logs"][0].get("is_excused") is not True


def test_second_review_after_approval_is_refused(base):
    base.tables["leave_requests"] = [_leave()]
    ls.review_leave("L1", TEACHER, True)
    assert ls.review_leave("L1", TEACHER, False)[1] == "Request was already reviewed."


def test_review_note_is_truncated_to_300_chars(base):
    base.tables["leave_requests"] = [_leave()]
    ls.review_leave("L1", TEACHER, True, "x" * 500)
    assert len(base.tables["leave_requests"][0]["review_note"]) == 300


# ── certificate access ──────────────────────────────────────────────

def test_document_url_none_when_no_certificate(base):
    base.tables["leave_requests"] = [_leave(document_path=None)]
    assert ls.get_document_url("L1", TEACHER) is None


def test_document_url_refused_for_other_teacher_without_touching_storage(base):
    base.tables["leave_requests"] = [_leave(document_path="5/abc.pdf")]
    assert ls.get_document_url("L1", OTHER_TEACHER) is None
