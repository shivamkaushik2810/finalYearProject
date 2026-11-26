"""Read-only access to the PUBLISHED timetable for students, parents and teachers.
Drafts are never read here. Publishing is the only way a version becomes visible to portal users."""
import re

from src.database.config import supabase
from src.services.timetable_service import load_entries, require_admin


class PublishError(ValueError):
    """A rule was broken. The message is safe to show to the user."""


def published_version():
    rows = (supabase.table("timetable_versions").select("id,label,published_at")
            .eq("status", "published").limit(1).execute().data or [])
    return rows[0] if rows else None


def published_entries(version_id):
    return load_entries(version_id)


def section_code_for_student(year, section):
    digits = re.sub(r"\D", "", str(year or ""))
    sec = str(section or "").strip().upper()
    if not digits or not sec:
        return None
    return f"{digits}{sec}"


def teacher_code_for(teacher_id):
    rows = (supabase.table("teacher_codes").select("code")
            .eq("teacher_id", str(teacher_id)).limit(1).execute().data or [])
    return rows[0]["code"] if rows else None


def entries_for_section(entries, section_code):
    return [e for e in entries if e.section_code == section_code]


def entries_for_teacher(entries, code):
    return [e for e in entries if e.faculty_code == code]


def publish_version(admin_id, version_id):
    require_admin(admin_id)
    try:
        supabase.rpc("timetable_publish", {"p_version_id": int(version_id),
                                           "p_actor": str(admin_id)}).execute()
    except Exception as exc:
        msg = str(exc)
        if "only a draft" in msg:
            raise PublishError("Only a draft can be published.") from exc
        if "empty" in msg:
            raise PublishError("An empty timetable cannot be published.") from exc
        raise PublishError("The database refused the publish. Nothing changed.") from exc
    return True
