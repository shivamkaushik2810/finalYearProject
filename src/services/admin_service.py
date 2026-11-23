"""Admin-only operations. Every public function checks the admin session first."""
import os
from datetime import date

from src.analytics.access import require_admin
from src.database.config import supabase

VALID_STATUS = ("pending", "approved", "rejected")


def list_teachers(status=None):
    require_admin()
    q = supabase.table("teachers").select(
        "teacher_id, username, name, email, status, failed_attempts, locked_until")
    if status:
        q = q.eq("status", status)
    return q.order("name").execute().data or []


def locked_teachers():
    return [t for t in list_teachers() if t.get("locked_until")]


def unlock_teacher(teacher_id):
    require_admin()
    supabase.table("teachers").update(
        {"failed_attempts": 0, "locked_until": None}).eq("teacher_id", teacher_id).execute()
    return True


def set_status(teacher_id, status):
    require_admin()
    if status not in VALID_STATUS:
        raise ValueError("Invalid status")
    supabase.table("teachers").update({"status": status}).eq("teacher_id", teacher_id).execute()
    return True


def deactivate_teacher(teacher_id):
    return set_status(teacher_id, "rejected")


def reactivate_teacher(teacher_id):
    return set_status(teacher_id, "approved")


def email_quota_today():
    require_admin()
    limit = int(os.environ.get("EMAIL_DAILY_LIMIT", "400"))
    rows = supabase.table("email_quota_usage").select("sent").eq(
        "day", date.today().isoformat()).execute().data or []
    sent = int(rows[0]["sent"]) if rows else 0
    return {"sent": sent, "limit": limit, "remaining": max(0, limit - sent)}


def list_corrections(teacher_id=None, limit=200):
    """Read-only view of attendance_audit_log (the table is append-only in the database)."""
    require_admin()
    rows = supabase.table("attendance_audit_log").select("*").order(
        "changed_at", desc=True).limit(limit).execute().data or []
    if teacher_id is not None:
        rows = [r for r in rows if str(r.get("changed_by")) == str(teacher_id)]
    return rows
