"""Manual substitution control and teacher accept or decline (Phase 6).
The authoritative checks are in sql/12_substitution_manual.sql. The Python checks here give
a clear reason before a write is attempted."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.database.config import supabase
from src.services import faculty_availability_service as avail
from src.services.substitution_manual_rules import validate_reason
from src.services.timetable_service import require_admin
from src.services.substitution_notify import notify_assigned, notify_unassigned

IST = ZoneInfo("Asia/Kolkata")
COLUMNS = ("id,version_id,substitution_date,weekday,period_no,section_code,subject_code,room,"
           "original_teacher_code,substitute_teacher_id,status,accepted_at")


class ManualError(ValueError):
    """A rule was broken. The message is safe to show to the user."""


def _friendly(exc):
    msg = str(exc)
    if "CONSECUTIVE" in msg:
        return "This would give the teacher more than 3 teaching periods in a row."
    if "no_double_booking" in msg or "duplicate key" in msg:
        return "This teacher already covers another class in that period."
    if "already the substitute" in msg:
        return "That teacher is already the substitute for this class."
    if "not your assignment" in msg:
        return "This assignment is not yours, or it is no longer assigned."
    if "cannot change" in msg:
        return "This substitution can no longer be changed. Refresh and try again."
    if "no timetable code" in msg:
        return "That teacher has no timetable code, so they cannot be assigned."
    if "reason" in msg:
        return "A reason of at least 5 characters is required."
    return "The database refused the change. Nothing was saved."


def _row(sub_id):
    rows = (supabase.table("faculty_substitutions").select(COLUMNS)
            .eq("id", int(sub_id)).limit(1).execute().data or [])
    if not rows:
        raise ManualError("that substitution no longer exists")
    row = rows[0]
    row["substitution_date"] = date.fromisoformat(str(row["substitution_date"])[:10])
    return row


def my_substitutions(teacher_id, start=None, days=14):
    """Assigned substitutions for this teacher in a date window. Only their own rows."""
    start = start or datetime.now(IST).date()
    end = start + timedelta(days=days)
    try:
        return (supabase.table("faculty_substitutions")
                .select("id,substitution_date,period_no,section_code,subject_code,room,"
                        "original_teacher_code,status,accepted_at")
                .eq("substitute_teacher_id", str(teacher_id))
                .eq("status", "assigned")
                .gte("substitution_date", start.isoformat())
                .lte("substitution_date", end.isoformat())
                .order("substitution_date").order("period_no")
                .limit(200).execute().data or [])
    except Exception as exc:
        raise ManualError("Your substitutions could not be loaded.") from exc


def accept_substitution(teacher_id, sub_id):
    _row(sub_id)
    try:
        supabase.rpc("faculty_substitution_accept", {
            "p_id": int(sub_id), "p_teacher_id": str(teacher_id),
            "p_actor": f"teacher:{teacher_id}"}).execute()
    except Exception as exc:
        raise ManualError(_friendly(exc)) from exc
    return True


def decline_substitution(teacher_id, sub_id, reason):
    err = validate_reason(reason)
    if err:
        raise ManualError(err)
    _row(sub_id)
    try:
        supabase.rpc("faculty_substitution_decline", {
            "p_id": int(sub_id), "p_teacher_id": str(teacher_id),
            "p_reason": reason.strip(), "p_actor": f"teacher:{teacher_id}"}).execute()
    except Exception as exc:
        raise ManualError(_friendly(exc)) from exc
    notify_unassigned(sub_id)
    return True


def candidate_options(admin_id, version_id, sub_id):
    """Every linked teacher except the original, with eligibility and the reasons if refused."""
    require_admin(admin_id)
    row = _row(sub_id)
    names = {str(t["teacher_id"]): t["name"]
             for t in supabase.table("teachers").select("teacher_id,name").execute().data or []}
    options = []
    for c in supabase.table("teacher_codes").select("code,teacher_id").execute().data or []:
        if c["code"] == row["original_teacher_code"]:
            continue
        tid = str(c["teacher_id"])
        try:
            res = avail.check_eligibility(admin_id, version_id, tid, row["subject_code"],
                                          row["weekday"], row["period_no"], row["substitution_date"])
            eligible, reasons = res["eligible"], res["reasons"]
        except avail.PlanningError as exc:
            eligible, reasons = False, [str(exc)]
        options.append({"code": c["code"], "teacher_id": tid, "name": names.get(tid, ""),
                        "eligible": eligible, "reasons": reasons})
    options.sort(key=lambda o: (not o["eligible"], o["code"]))
    return options


def override_substitution(admin_id, sub_id, teacher_id, reason, force=False):
    require_admin(admin_id)
    err = validate_reason(reason)
    if err:
        raise ManualError(err)
    row = _row(sub_id)
    res = avail.check_eligibility(admin_id, row["version_id"], str(teacher_id), row["subject_code"],
                                  row["weekday"], row["period_no"], row["substitution_date"])
    note = reason.strip()
    if not res["eligible"]:
        if not force:
            raise ManualError("Not eligible: " + "; ".join(res["reasons"])
                              + ". Tick 'Override anyway' and give a reason to proceed.")
        note += " [forced: " + "; ".join(res["reasons"]) + "]"
    try:
        supabase.rpc("faculty_substitution_override", {
            "p_id": int(sub_id), "p_teacher_id": str(teacher_id),
            "p_reason": note[:500], "p_actor": str(admin_id)}).execute()
    except Exception as exc:
        raise ManualError(_friendly(exc)) from exc
    notify_assigned(sub_id)
    return True
