"""Faculty absence requests and decisions. Every write calls a SQL function from
sql/08_faculty_absence.sql, so the overlap check and the audit row happen in one transaction."""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.database.config import supabase
from src.services.faculty_absence_rules import normalise_periods, validate_absence
from src.services.timetable_service import require_admin

IST = ZoneInfo("Asia/Kolkata")
LIST_LIMIT = 200


class AbsenceError(ValueError):
    """A rule was broken. The message is safe to show to the user."""


def _today():
    return datetime.now(IST).date()


def _friendly(exc):
    msg = str(exc)
    if "CLASH" in msg:
        return "This teacher already has an absence that overlaps these dates or periods."
    if "cannot change an absence" in msg:
        return "This absence has already been decided. Refresh the list and try again."
    if "not found" in msg:
        return "That absence no longer exists."
    return "The database refused the change. Nothing was saved."


def request_absence(actor_role, actor_id, teacher_id, start, end, kind, periods, reason, today=None):
    """Teachers may request only their own planned absence (status pending).
    Administrators record any absence (status approved), including emergency and unplanned."""
    if actor_role == "teacher":
        if str(actor_id) != str(teacher_id):
            raise PermissionError("teachers can only request their own absence")
        if kind != "planned":
            raise AbsenceError("only an administrator can record emergency or unplanned absences")
        status, approved_by, is_admin = "pending", None, False
    elif actor_role == "admin":
        require_admin(actor_id)
        status, approved_by, is_admin = "approved", str(actor_id), True
    else:
        raise PermissionError("unknown role")

    periods_n = normalise_periods(periods)
    errors = validate_absence(start, end, kind, periods_n, reason, today or _today(), is_admin)
    if errors:
        raise AbsenceError("; ".join(errors))

    try:
        res = supabase.rpc("faculty_absence_create", {
            "p_teacher_id": str(teacher_id), "p_start": start.isoformat(), "p_end": end.isoformat(),
            "p_kind": kind, "p_periods": periods_n, "p_reason": reason.strip(),
            "p_requested_by": f"{actor_role}:{actor_id}", "p_status": status,
            "p_approved_by": approved_by}).execute()
    except Exception as exc:
        raise AbsenceError(_friendly(exc)) from exc
    return res.data


def decide_absence(admin_id, absence_id, decision, note=""):
    require_admin(admin_id)
    if decision not in ("approved", "rejected", "cancelled"):
        raise AbsenceError("unknown decision")
    try:
        res = supabase.rpc("faculty_absence_decide", {
            "p_id": int(absence_id), "p_new_status": decision,
            "p_actor": str(admin_id), "p_note": (note or "")[:300]}).execute()
    except Exception as exc:
        raise AbsenceError(_friendly(exc)) from exc
    return res.data


def list_absences(admin_id=None, teacher_id=None, status=None):
    query = supabase.table("faculty_absences").select(
        "id,teacher_id,start_date,end_date,kind,periods,reason,status,"
        "requested_by,approved_by,decision_note,decided_at,created_at")
    if admin_id is not None:
        require_admin(admin_id)
    elif teacher_id is not None:
        query = query.eq("teacher_id", str(teacher_id))
    else:
        raise PermissionError("an administrator or a teacher is required")
    if status:
        query = query.eq("status", status)
    return query.order("start_date", desc=True).limit(LIST_LIMIT).execute().data or []
