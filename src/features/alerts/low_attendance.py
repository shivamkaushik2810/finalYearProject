"""Low-attendance warnings to students and parents (email; WhatsApp/SMS only for opted-in numbers).

Reads the student_subject_stats view. Safe to re-run: alert_service.claim()
allows one notice per student + channel + kind + ISO week, so a retry never double-sends.
One student's failure never stops the others."""
import html
import logging

from src.database.config import supabase
from src.services import alert_service as alerts
from src.services import email_service as mail
from src.services.db_utils import fetch_all
from src.services.email_rules import emails_conflict
from src.services.pure_logic import iso_week_key, normalize_phone

log = logging.getLogger("snapclass.low_attendance")

KIND = "low_attendance"
THRESHOLD = 75.0
MIN_CLASSES = 5
DEFAULT_MAX_EMAILS = 400          # stay under the Gmail daily cap; the rest go out on the next run
CHUNK = 100


# ───────────── database reads (kept tiny so tests can replace them) ─────────────

def _view_rows():
    """Per student and subject counts from the student_subject_stats view the app already uses."""
    rows = fetch_all(lambda: supabase.table("student_subject_stats")
                     .select("student_id, subject_id, total, present")
                     .order("student_id").order("subject_id"))
    return [{"student_id": r["student_id"], "subject_id": r["subject_id"],
             "total_classes": r.get("total"), "present_classes": r.get("present")} for r in rows]


def _by_ids(table, key, cols, ids):
    out, ids = {}, sorted({str(i) for i in ids})
    for i in range(0, len(ids), CHUNK):
        for r in supabase.table(table).select(cols).in_(key, ids[i:i + CHUNK]).execute().data or []:
            out[str(r[key])] = r
    return out


_BASIC_COLS = "student_id, name, email, parent_name, parent_email"
_PHONE_COLS = _BASIC_COLS + ", phone, parent_phone, alert_opt_in"


def _people(ids):
    """Phone and consent columns are optional (sql 04_batch2.sql). Without them the job still sends email."""
    try:
        return _by_ids("students", "student_id", _PHONE_COLS, ids)
    except Exception as e:
        if "42703" not in str(e) and "does not exist" not in str(e):
            raise
        log.warning("phone/consent columns not found; sending email only")
        return _by_ids("students", "student_id", _BASIC_COLS, ids)


def _subject_names(ids):
    return {k: v.get("name") or "Subject" for k, v in _by_ids("subjects", "subject_id", "subject_id, name", ids).items()}


# ───────────── pure logic ─────────────

def group_low(rows, threshold=THRESHOLD, min_classes=MIN_CLASSES):
    """{student_id: [{subject_id, total, present, pct}]} for subjects below the threshold.
    Subjects with fewer than min_classes classes are ignored (too early to judge)."""
    out = {}
    for r in rows or []:
        total, present = int(r.get("total_classes") or 0), int(r.get("present_classes") or 0)
        if total < min_classes:
            continue
        pct = round(present / total * 100, 1)
        if pct < threshold:
            out.setdefault(str(r["student_id"]), []).append(
                {"subject_id": str(r["subject_id"]), "total": total, "present": present, "pct": pct})
    for items in out.values():
        items.sort(key=lambda x: x["pct"])
    return out


def _usable_email(addr):
    a = (addr or "").strip()
    return bool(a) and "@" in a and not a.lower().endswith(".invalid")


def build_email(student_name, parent_name, items, names, threshold, for_parent):
    who = (parent_name or "Parent") if for_parent else (student_name or "Student")
    about = f"your ward {student_name}" if for_parent else "you"
    lines = [f"{names.get(i['subject_id'], 'Subject')}: {i['present']}/{i['total']} ({i['pct']}%)" for i in items]
    plain = (f"Dear {who},\n\nAttendance of {about} is below {threshold:.0f}% in:\n  "
             + "\n  ".join(lines) + "\n\nPlease encourage regular attendance.\n\nSnapClass (automated message)\n")
    rows = "".join(f"<li>{html.escape(l)}</li>" for l in lines)
    body = (f"<div style='font-family:Arial,sans-serif;max-width:600px'>"
            f"<h3 style='color:#A32D2D'>Low attendance warning</h3>"
            f"<p>Dear <b>{html.escape(who)}</b>,</p>"
            f"<p>Attendance of {html.escape(about)} is below <b>{threshold:.0f}%</b> in:</p><ul>{rows}</ul>"
            f"<p>Please encourage regular attendance.</p>"
            f"<p style='color:#64748b;font-size:12px'>SnapClass (automated message)</p></div>")
    subject = f"Low attendance warning: {student_name}" if for_parent else "Low attendance warning"
    return subject, body, plain


# ───────────── the job ─────────────

def run(dry_run=False, max_emails=DEFAULT_MAX_EMAILS, threshold=THRESHOLD, min_classes=MIN_CLASSES, today=None,
        test_email=None):
    period = iso_week_key(today)
    low = group_low(_view_rows(), threshold, min_classes)
    res = {"period": period, "flagged": len(low), "emails_sent": 0, "messages_sent": 0,
           "already_sent": 0, "failed": 0, "deferred": 0, "dry_run": bool(dry_run)}
    if not low:
        return res
    people = _people(low.keys())
    names = _subject_names({i["subject_id"] for items in low.values() for i in items})
    mode = alerts.channel_mode()

    def deliver(sid, channel, send, is_email):
        if test_email:                      # test mode: send to your own address only, record nothing
            try:
                send()
                res["emails_sent"] += 1
            except Exception as e:
                res["failed"] += 1
                log.warning("test send failed: %s", type(e).__name__)
            return
        if dry_run:
            res["emails_sent" if is_email else "messages_sent"] += 1
            return
        if not alerts.claim(sid, KIND, channel, period):
            res["already_sent"] += 1
            return
        try:
            ok = send()
            if ok is False:
                raise RuntimeError("send refused")
        except Exception as e:
            alerts.release(sid, KIND, channel, period)          # free the slot so the next run retries
            res["failed"] += 1
            log.warning("low-attendance send failed (%s): %s", channel, type(e).__name__)
            return
        alerts.mark_sent(sid, KIND, channel, period)
        res["emails_sent" if is_email else "messages_sent"] += 1

    for sid, items in low.items():
        p = people.get(sid)
        if not p:
            continue
        try:
            targets = []
            if _usable_email(p.get("email")):
                targets.append(("email_student", p["email"], False))
            if _usable_email(p.get("parent_email")) and not emails_conflict(p.get("email"), p.get("parent_email")):
                targets.append(("email_parent", p["parent_email"], True))
            for channel, addr, for_parent in targets:
                addr = test_email or addr
                if res["emails_sent"] >= max_emails:
                    res["deferred"] += 1
                    continue
                subj, body, plain = build_email(p.get("name"), p.get("parent_name"), items, names, threshold, for_parent)
                if test_email:
                    subj = "[TEST] " + subj
                deliver(sid, channel, lambda a=addr, s=subj, b=body, t=plain: mail._send(a, s, b, t), True)
            if mode != "off" and p.get("alert_opt_in") and not test_email:
                short = "; ".join(f"{names.get(i['subject_id'], 'Subject')} {i['pct']}%" for i in items[:3])
                for channel, raw, who in (("msg_student", p.get("phone"), "Your"),
                                          ("msg_parent", p.get("parent_phone"), f"{p.get('name') or 'Your ward'}'s")):
                    phone = normalize_phone(raw)
                    if phone:
                        text = f"SnapClass: {who} attendance is below {threshold:.0f}% ({short}). Please attend regularly."
                        deliver(sid, channel, lambda ph=phone, t=text: alerts.send_message(ph, t)[0], False)
        except Exception as e:
            res["failed"] += 1
            log.warning("low-attendance student skipped: %s", type(e).__name__)
    return res
