"""Glue between substitution actions and the notification outbox. Never raises: a failure to queue
a notice must not undo or block the timetable change. Failures are returned so the UI can warn."""
from src.database.config import supabase
from src.services import notification_service as nsvc


def _teacher(teacher_id):
    rows = (supabase.table("teachers").select("teacher_id,name,email")
            .eq("teacher_id", str(teacher_id)).limit(1).execute().data or [])
    return rows[0] if rows else None


def _code_to_teacher(code):
    rows = (supabase.table("teacher_codes").select("teacher_id")
            .eq("code", code).limit(1).execute().data or [])
    return str(rows[0]["teacher_id"]) if rows else None


def _sub(sub_id):
    rows = (supabase.table("faculty_substitutions")
            .select("id,substitution_date,period_no,section_code,subject_code,room,"
                    "original_teacher_code,substitute_teacher_id,reasons")
            .eq("id", int(sub_id)).limit(1).execute().data or [])
    return rows[0] if rows else None


def notify_assigned(sub_id):
    """Assignment confirmed or changed: tell the substitute and the original teacher."""
    try:
        sub = _sub(sub_id)
        if not sub or not sub.get("substitute_teacher_id"):
            return None
        sub_t = _teacher(sub["substitute_teacher_id"])
        orig_tid = _code_to_teacher(sub["original_teacher_code"])
        orig_t = _teacher(orig_tid) if orig_tid else None
        nsvc.notify_assignment(
            {**sub, "substitution_date": str(sub["substitution_date"])},
            sub["substitute_teacher_id"], (sub_t or {}).get("email"),
            orig_tid, (orig_t or {}).get("email"),
            (sub_t or {}).get("name") or "A colleague")
        return None
    except Exception as exc:
        print(f"notify_assigned failed: {type(exc).__name__}")
        return "The change was saved, but the notice could not be queued. It will not be re-sent automatically."


def notify_unassigned(sub_id, admin_email=None):
    """Class is unassigned again: tell the administrator."""
    try:
        sub = _sub(sub_id)
        if not sub:
            return None
        nsvc.notify_unassigned({**sub, "substitution_date": str(sub["substitution_date"])}, admin_email)
        return None
    except Exception as exc:
        print(f"notify_unassigned failed: {type(exc).__name__}")
        return "The change was saved, but the administrator notice could not be queued."
