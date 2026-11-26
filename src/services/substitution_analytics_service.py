"""Substitution analytics data (Phase 8). Read-only and admin-only."""
from datetime import timedelta

from src.database.config import supabase
from src.services.timetable_service import require_admin

PAGE = 1000
MAX_WINDOW_DAYS = 366


def _all(build):
    out, start = [], 0
    while True:
        chunk = build().range(start, start + PAGE - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < PAGE:
            return out
        start += PAGE


def load(admin_id, version_id, start, end):
    require_admin(admin_id)
    if start > end:
        raise ValueError("the start date is after the end date")
    if (end - start) > timedelta(days=MAX_WINDOW_DAYS):
        raise ValueError("choose a window of one year or less")
    rows = _all(lambda: supabase.table("faculty_substitutions")
                .select("id,substitution_date,section_code,subject_code,original_teacher_code,"
                        "substitute_teacher_id,status,reasons,created_at")
                .eq("version_id", int(version_id))
                .gte("substitution_date", start.isoformat())
                .lte("substitution_date", end.isoformat())
                .order("id"))
    names = {str(t["teacher_id"]): t["name"]
             for t in _all(lambda: supabase.table("teachers").select("teacher_id,name").order("teacher_id"))}
    for r in rows:
        tid = r.get("substitute_teacher_id")
        r["substitute_name"] = names.get(str(tid), "") if tid else ""
    ids = {r["id"] for r in rows}
    events = [e for e in _all(lambda: supabase.table("faculty_substitution_events")
                              .select("substitution_id,action,at").order("id"))
              if e["substitution_id"] in ids]
    return rows, events
