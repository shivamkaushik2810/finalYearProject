"""Substitution notices (Phase 7). Writes to the outbox and inbox through SQL, sends email
through the existing SMTP settings, and retries failures. Never sends the same notice twice."""
import smtplib
from email.mime.text import MIMEText

from src.database.config import supabase
from src.services import notification_messages as msg
from src.services.smtp_config import get_smtp_settings, open_smtp

BATCH = 50


def enqueue(event, sub_id, kind, teacher_id, email, subject, body):
    recipient = str(teacher_id) if teacher_id else kind
    key = msg.key_for(event, sub_id, recipient)
    res = supabase.rpc("notification_enqueue", {
        "p_key": key, "p_kind": kind,
        "p_teacher_id": str(teacher_id) if teacher_id else None,
        "p_email": email or "", "p_subject": subject, "p_body": body}).execute()
    return bool(res.data)


def notify_assignment(sub, substitute_teacher_id, substitute_email, original_teacher_id, original_email,
                      substitute_name, admin_email=None):
    """Called once per confirmed or overridden assignment. Each recipient gets one notice."""
    queued = 0
    s, b = msg.assigned_to_substitute(sub)
    queued += enqueue("assigned", sub["id"], "teacher", substitute_teacher_id, substitute_email, s, b)
    s, b = msg.absence_for_original(sub, substitute_name)
    queued += enqueue("covered", sub["id"], "teacher", original_teacher_id, original_email, s, b)
    return queued


def notify_unassigned(sub, admin_email=None):
    s, b = msg.unassigned_for_admin(sub)
    return enqueue("unassigned", sub["id"], "admin", None, admin_email, s, b)


def _send_one(server, sender, row):
    mail = MIMEText(row["body"], "plain", "utf-8")
    mail["Subject"] = row["subject"]
    mail["From"] = f"SnapClass <{sender}>"
    mail["To"] = row["recipient_email"]
    server.sendmail(sender, row["recipient_email"], mail.as_string())


def deliver_due(limit=BATCH):
    """Sends due emails once each. Safe to run repeatedly and from several workers at once."""
    claimed = supabase.rpc("notification_claim", {"p_limit": int(limit)}).execute().data or []
    if not claimed:
        return {"claimed": 0, "sent": 0, "failed": 0}
    sent = failed = 0
    try:
        server, cfg = open_smtp()
    except Exception as exc:
        for row in claimed:
            supabase.rpc("notification_mark", {"p_id": row["id"], "p_ok": False,
                                               "p_error": f"smtp connect: {type(exc).__name__}"}).execute()
            failed += 1
        return {"claimed": len(claimed), "sent": 0, "failed": failed}
    try:
        for row in claimed:
            if not row.get("recipient_email"):
                supabase.rpc("notification_mark", {"p_id": row["id"], "p_ok": False,
                                                   "p_error": "no email address on file"}).execute()
                failed += 1
                continue
            try:
                _send_one(server, cfg["sender"], row)
            except Exception as exc:
                supabase.rpc("notification_mark", {"p_id": row["id"], "p_ok": False,
                                                   "p_error": type(exc).__name__}).execute()
                failed += 1
            else:
                supabase.rpc("notification_mark", {"p_id": row["id"], "p_ok": True,
                                                   "p_error": None}).execute()
                sent += 1
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return {"claimed": len(claimed), "sent": sent, "failed": failed}


def my_inbox(teacher_id, limit=50):
    return (supabase.table("notification_inbox").select("id,subject,body,read_at,created_at")
            .eq("teacher_id", str(teacher_id)).order("created_at", desc=True)
            .limit(limit).execute().data or [])


def mark_read(teacher_id, inbox_id):
    supabase.table("notification_inbox").update({"read_at": "now()"}).eq("id", int(inbox_id)) \
        .eq("teacher_id", str(teacher_id)).execute()
    return True
