"""Background e-mail queue: one worker, one reused Gmail connection per job,
daily-quota guard, and accurate per-reason results."""
import logging
import os
import queue
import smtplib
import threading
import time
import uuid

from src.database.config import supabase
from src.services import email_service as es

log = logging.getLogger("snapclass.email")

DAILY_LIMIT = int(os.environ.get("EMAIL_DAILY_LIMIT", "400"))  # stay under Gmail's cap
SEND_DELAY = float(os.environ.get("EMAIL_SEND_DELAY", "0.2"))
JOB_TTL_SECONDS = 3600

_QUEUE = queue.Queue()
_JOBS, _KEYS = {}, {}
_LOCK = threading.Lock()
_WORKER = None


def classify_smtp_error(exc):
    """'blocked' (stop the batch), 'invalid' (bad address), 'retry' (reconnect), 'failed'."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "blocked"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "invalid"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "retry"
    code = getattr(exc, "smtp_code", None)
    raw = getattr(exc, "smtp_error", b"") or b""
    text = (raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)).lower()
    if code in (421, 450, 451, 452):
        return "blocked"
    if code == 550 and ("5.4.5" in text or "quota" in text or "limit" in text):
        return "blocked"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "blocked"
    if isinstance(exc, OSError) and not isinstance(exc, smtplib.SMTPException):
        return "retry"  # socket timeout / reset
    return "failed"


def _short(exc):
    return f"{type(exc).__name__}: {str(exc)[:120]}"


def _reserve_quota(n):
    try:
        res = supabase.rpc("reserve_email_quota", {"p_count": n, "p_limit": DAILY_LIMIT}).execute()
        return int(res.data)
    except Exception:
        log.exception("quota reservation failed; sending without quota guard")
        return n


def _build_job(logs, subject_name, subject_code, teacher_name, teacher_email,
               timestamp, enrolled):
    student_map = {s["student_id"]: s for s in enrolled}
    present, recipients, no_email = [], [], []
    for entry in logs:
        if not entry.get("is_present"):
            continue
        student = student_map.get(entry["student_id"])
        if not student:
            continue
        present.append(student)
        if student.get("email"):
            recipients.append(student)
        else:
            no_email.append(student["name"])
    return {
        "id": uuid.uuid4().hex, "status": "queued", "created": time.time(),
        "subject_name": subject_name, "subject_code": subject_code,
        "teacher_name": teacher_name, "teacher_email": teacher_email,
        "timestamp": timestamp, "enrolled_count": len(enrolled),
        "present_students": present, "recipients": recipients,
        "no_email": no_email,
        "sent": 0, "failed": [], "deferred": 0,
        "block_reason": None, "teacher_status": None,
    }


def enqueue_attendance_emails(logs, subject_name, subject_code, teacher_name,
                              teacher_email, timestamp, enrolled):
    """Queue emails for the given (newly inserted) logs. Returns job id or None."""
    if not logs:
        return None
    key = f"{logs[0]['subject_id']}|{timestamp}"
    with _LOCK:
        _prune_locked()
        if key in _KEYS:  # same session queued twice -> same job, no 2nd batch
            return _KEYS[key]
        job = _build_job(logs, subject_name, subject_code, teacher_name,
                         teacher_email, timestamp, enrolled)
        if not teacher_email and not job["recipients"] and not job["no_email"]:
            return None
        _JOBS[job["id"]] = job
        _KEYS[key] = job["id"]
        job["key"] = key
        _ensure_worker_locked()
    _QUEUE.put(job)
    return job["id"]


def get_job(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        return {k: (list(v) if isinstance(v, list) else v)
                for k, v in job.items() if k not in ("recipients", "present_students")}


def _prune_locked():
    cutoff = time.time() - JOB_TTL_SECONDS
    for jid in [j for j, job in _JOBS.items()
                if job["created"] < cutoff and job["status"] in ("done", "error")]:
        _KEYS.pop(_JOBS[jid].get("key"), None)
        del _JOBS[jid]


def _ensure_worker_locked():
    global _WORKER
    if _WORKER is None or not _WORKER.is_alive():
        _WORKER = threading.Thread(target=_loop, daemon=True, name="snapclass-mailer")
        _WORKER.start()


def _loop():
    while True:
        job = _QUEUE.get()
        try:
            _run(job)
        except Exception:
            log.exception("email job crashed")
            job["status"] = "error"
        finally:
            _QUEUE.task_done()


def _defer(job, items, reason):
    if not items:
        return
    job["deferred"] += len(items)
    job["block_reason"] = job["block_reason"] or reason
    if any(kind == "teacher" for kind, _ in items):
        job["teacher_status"] = "deferred"


def _deliver(job, kind, student):
    if kind == "teacher":
        es.send_teacher_summary_email(
            job["teacher_name"], job["teacher_email"], job["subject_name"],
            job["subject_code"], job["timestamp"], job["present_students"],
            job["enrolled_count"])
    else:
        es.send_student_attendance_email(
            student["name"], student["email"], job["subject_name"],
            job["subject_code"], job["teacher_name"], job["timestamp"])


def _send_one(job, kind, student):
    for attempt in (1, 2):
        try:
            _deliver(job, kind, student)
        except Exception as exc:
            outcome = classify_smtp_error(exc)
            if outcome == "retry" and attempt == 1:
                try:
                    es.smtp_close()
                    es.smtp_open()
                    continue
                except Exception as exc2:
                    exc, outcome = exc2, "blocked"
            if outcome == "retry":
                outcome = "blocked"
            if outcome == "blocked":
                log.error("Gmail blocked/limited the batch: %s", _short(exc))
                _defer(job, [(kind, student)], _short(exc))
                return "blocked"
            if kind == "teacher":
                job["teacher_status"] = "failed"
            else:
                reason = "address rejected" if outcome == "invalid" else _short(exc)
                job["failed"].append((student["name"], reason))
            log.warning("send failed (%s) for %s", outcome, kind)
            return "failed"
        else:
            if kind == "teacher":
                job["teacher_status"] = "sent"
            else:
                job["sent"] += 1
            return "ok"
    return "failed"


def _run(job):
    job["status"] = "running"
    items = []
    if job["teacher_email"]:
        items.append(("teacher", None))
    else:
        job["teacher_status"] = "no_email"
    items += [("student", s) for s in job["recipients"]]
    if not items:
        job["status"] = "done"
        return

    granted = max(0, min(len(items), _reserve_quota(len(items))))
    sendable, over = items[:granted], items[granted:]
    _defer(job, over, "daily_limit")
    if not sendable:
        job["status"] = "done"
        return

    try:
        es.smtp_open()
    except Exception as exc:
        log.error("Gmail connect/login failed: %s", _short(exc))
        _defer(job, sendable, f"could not log in to Gmail ({type(exc).__name__})")
        job["status"] = "done"
        return

    try:
        for i, (kind, student) in enumerate(sendable):
            if _send_one(job, kind, student) == "blocked":
                _defer(job, sendable[i + 1:], job["block_reason"])
                break
            time.sleep(SEND_DELAY)
    finally:
        es.smtp_close()
    job["status"] = "done"
