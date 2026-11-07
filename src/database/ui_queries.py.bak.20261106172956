"""Batched, paginated reads used by the refreshed UI. Replaces one-query-per-student loops."""
from src.database.config import supabase

PAGE = 1000


def _fetch_all(build):
    """Supabase returns at most 1000 rows per request, so page through the result."""
    rows, start = [], 0
    while True:
        data = build(start, start + PAGE - 1).data or []
        rows.extend(data)
        if len(data) < PAGE:
            return rows
        start += PAGE


def get_logs_for_subjects(subject_ids):
    ids = [i for i in subject_ids if i]
    if not ids:
        return []
    return _fetch_all(lambda a, b: supabase.table("attendance_logs")
                      .select("student_id, subject_id, timestamp, is_present")
                      .in_("subject_id", ids)
                      .order("timestamp").order("subject_id").order("student_id")
                      .range(a, b).execute())


def get_enrolled_students(subject_id):
    res = (supabase.table("subject_students")
           .select("student_id, students(student_id, name, email, roll_no, section, parent_email)")
           .eq("subject_id", subject_id).execute())
    return [n["students"] for n in (res.data or []) if n.get("students")]


def get_student_by_id(student_id):
    res = supabase.table("students").select("*").eq("student_id", student_id).limit(1).execute()
    return res.data[0] if res.data else None


def get_student_names(student_ids):
    ids = [i for i in student_ids if i]
    if not ids:
        return {}
    res = supabase.table("students").select("student_id, name, roll_no").in_("student_id", ids).execute()
    return {s["student_id"]: s for s in (res.data or [])}
