"""Faculty planning data and the eligibility check. Writes call the SQL functions in
sql/09_faculty_planning.sql, which record the audit row in the same transaction."""
from datetime import date

from src.database.config import supabase
from src.services.faculty_availability_rules import (
    LEVELS, PlanningError, eligibility_reasons, free_periods, validate_limits, validate_unavailability)
from src.services.timetable_service import load_entries, require_admin


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _teacher(teacher_id):
    rows = (supabase.table("teachers").select("teacher_id,status")
            .eq("teacher_id", str(teacher_id)).limit(1).execute().data or [])
    if not rows:
        raise PlanningError("teacher not found")
    return rows[0]


def _code(teacher_id):
    rows = (supabase.table("teacher_codes").select("code")
            .eq("teacher_id", str(teacher_id)).limit(1).execute().data or [])
    return rows[0]["code"] if rows else None


def _quals(teacher_id):
    rows = (supabase.table("faculty_subject_qualifications").select("subject_code,level,is_active")
            .eq("teacher_id", str(teacher_id)).execute().data or [])
    return {r["subject_code"]: r for r in rows}


def _rules(teacher_id):
    rows = (supabase.table("faculty_unavailability")
            .select("weekday,period_no,effective_from,effective_until,reason")
            .eq("teacher_id", str(teacher_id)).execute().data or [])
    return [{**r,
             "effective_from": _d(r["effective_from"]),
             "effective_until": _d(r["effective_until"]) if r.get("effective_until") else None}
            for r in rows]


def _limits(teacher_id):
    rows = (supabase.table("faculty_limits").select("max_daily_periods,max_weekly_periods")
            .eq("teacher_id", str(teacher_id)).limit(1).execute().data or [])
    if not rows:
        return None
    return {"max_daily": rows[0]["max_daily_periods"], "max_weekly": rows[0]["max_weekly_periods"]}


def _absences(teacher_id):
    rows = (supabase.table("faculty_absences").select("status,start_date,end_date,periods")
            .eq("teacher_id", str(teacher_id)).execute().data or [])
    return [{"status": r["status"], "start_date": _d(r["start_date"]),
             "end_date": _d(r["end_date"]), "periods": r.get("periods")} for r in rows]


def check_eligibility(admin_id, version_id, teacher_id, subject_code, weekday, period, on_date):
    """Read-only. Returns eligible, the reasons it is not, and the teacher's free periods that day."""
    require_admin(admin_id)
    teacher = _teacher(teacher_id)
    code = _code(teacher_id)
    entries = load_entries(version_id) if code else []
    rules = _rules(teacher_id)
    absences = _absences(teacher_id)
    reasons = eligibility_reasons(
        code=code, subject_code=subject_code, weekday=weekday, period=period, on_date=on_date,
        entries=entries, quals=_quals(teacher_id), rules=rules, absences=absences,
        limits=_limits(teacher_id), teacher_status=teacher["status"])
    free = free_periods(code, weekday, on_date, entries, rules, absences)
    return {"eligible": not reasons, "reasons": reasons, "free_periods": free}


def _rpc(name, params):
    try:
        return supabase.rpc(name, params).execute().data
    except Exception as exc:
        if "CLASH" in str(exc):
            raise PlanningError("That change overlaps an existing record.") from exc
        raise PlanningError("The database refused the change. Nothing was saved.") from exc


def set_qualification(admin_id, teacher_id, subject_code, level, active):
    require_admin(admin_id)
    code = (subject_code or "").strip()
    if not 1 <= len(code) <= 40:
        raise PlanningError("subject code must be 1 to 40 characters")
    if level not in LEVELS:
        raise PlanningError("level must be trained, primary or secondary")
    _teacher(teacher_id)
    _rpc("faculty_qualification_set", {
        "p_teacher_id": str(teacher_id), "p_subject_code": code, "p_level": level,
        "p_active": bool(active), "p_actor": str(admin_id)})
    return True


def add_unavailability(admin_id, teacher_id, weekday, period, reason, start, until=None):
    require_admin(admin_id)
    errors = validate_unavailability(weekday, period, reason, start, until)
    if errors:
        raise PlanningError("; ".join(errors))
    _teacher(teacher_id)
    return _rpc("faculty_unavailability_add", {
        "p_teacher_id": str(teacher_id), "p_weekday": weekday, "p_period": period,
        "p_reason": reason.strip(), "p_from": start.isoformat(),
        "p_until": until.isoformat() if until else None, "p_actor": str(admin_id)})


def set_limits(admin_id, teacher_id, max_daily, max_weekly):
    require_admin(admin_id)
    errors = validate_limits(int(max_daily), int(max_weekly))
    if errors:
        raise PlanningError("; ".join(errors))
    _teacher(teacher_id)
    _rpc("faculty_limits_set", {
        "p_teacher_id": str(teacher_id), "p_max_daily": int(max_daily),
        "p_max_weekly": int(max_weekly), "p_actor": str(admin_id)})
    return True
