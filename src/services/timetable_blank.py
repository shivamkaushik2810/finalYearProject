"""Blank versions and adding single classes to a version (admin only). Every write goes through a
database function that checks the version and the clashes, and logs the change."""
from src.database.config import supabase
from src.services.timetable_draft import DraftError


def _message(exc):
    print(f"timetable_blank call failed: {type(exc).__name__}")
    msg = str(getattr(exc, "message", "") or exc).strip()
    return msg or "Could not save. Please try again."


def list_sections():
    return (supabase.table("sections").select("id,code").eq("is_active", True)
            .order("code").execute().data or [])


def create_blank_version(actor, label):
    name = (label or "").strip()
    if not name or len(name) > 80:
        raise DraftError("Enter a name for the new version (1 to 80 characters).")
    try:
        res = supabase.rpc("timetable_create_blank_version",
                           {"p_label": name, "p_actor": str(actor)}).execute()
    except Exception as exc:
        raise DraftError(_message(exc)) from None
    return res.data


def add_entry(actor, version_id, fields):
    try:
        res = supabase.rpc("timetable_add_entry", {
            "p_version_id": int(version_id),
            "p_section_id": int(fields["section_id"]),
            "p_weekday": int(fields["weekday"]),
            "p_period_no": int(fields["period_no"]),
            "p_block_len": int(fields["block_len"]),
            "p_kind": fields["kind"],
            "p_subject_code": fields.get("subject_code") or "",
            "p_subject_name": fields.get("subject_name") or "",
            "p_faculty_code": fields.get("faculty_code") or "",
            "p_room": fields.get("room") or "",
            "p_actor": str(actor),
        }).execute()
    except Exception as exc:
        raise DraftError(_message(exc)) from None
    return res.data
