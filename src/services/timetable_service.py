"""Admin-only access to timetable drafts.

Validation runs in Python and returns full messages. The write goes through the
apply_timetable_change SQL function, which locks the version, detects stale edits,
re-checks hard clashes, and writes the change log in one transaction.
Known limit: the consecutive-teaching rule is checked here, not in SQL, so two
simultaneous edits could in theory both pass it. Hard clashes are always enforced in SQL.
"""
from dataclasses import replace

from src.database.config import supabase
from src.services.timetable_validator import Entry, validate

EDITABLE = {"weekday", "period_no", "block_len", "kind", "subject_code",
            "subject_name", "faculty_code", "room"}
PAGE = 1000
COLUMNS = ("id,section_id,weekday,period_no,block_len,kind,subject_code,"
           "subject_name,faculty_code,room,sections(code)")


class NotAdmin(PermissionError):
    pass


def require_admin(admin_id):
    if not admin_id:
        raise NotAdmin("admin login required")
    rows = supabase.table("admins").select("id").eq("id", admin_id).limit(1).execute().data or []
    if not rows:
        raise NotAdmin("not an administrator")


def get_version(label):
    rows = (supabase.table("timetable_versions").select("id,label,status")
            .eq("label", label).limit(1).execute().data or [])
    if not rows:
        raise LookupError(f"no timetable version named '{label}'")
    return rows[0]


def _to_entry(r):
    sec = r.get("sections") or {}
    return Entry(id=r["id"], section_id=r["section_id"], section_code=sec.get("code", ""),
                 weekday=r["weekday"], period_no=r["period_no"], block_len=r["block_len"],
                 kind=r["kind"], subject_code=r.get("subject_code"),
                 subject_name=r.get("subject_name"), faculty_code=r.get("faculty_code"),
                 room=r.get("room"))


def load_entries(version_id):
    out, start = [], 0
    while True:
        chunk = (supabase.table("timetable_entries").select(COLUMNS)
                 .eq("version_id", version_id).order("id")
                 .range(start, start + PAGE - 1).execute().data or [])
        out.extend(_to_entry(r) for r in chunk)
        if len(chunk) < PAGE:
            return out
        start += PAGE


def check_change(admin_id, version_id, entry_id, changes):
    """Validate a proposed change without writing. Returns (entry_as_loaded, errors)."""
    require_admin(admin_id)
    unknown = set(changes) - EDITABLE
    if unknown:
        raise ValueError(f"not editable: {', '.join(sorted(unknown))}")
    entries = load_entries(version_id)
    current = next((e for e in entries if e.id == entry_id), None)
    if current is None:
        raise LookupError("entry not found in this version")
    candidate = replace(current, **changes)
    others = [e for e in entries if e.id != entry_id]
    return current, validate(candidate, others)


def apply_change(admin_id, version_id, entry_id, changes, actor, expected):
    """expected: the field values the admin saw. If the entry changed since, the save is refused."""
    current, errors = check_change(admin_id, version_id, entry_id, changes)
    if errors:
        return {"ok": False, "errors": errors}
    if not expected:
        return {"ok": False, "errors": ["The editor must send the values you loaded. Reload the entry and try again."]}
    try:
        res = supabase.rpc("apply_timetable_change", {
            "p_entry_id": entry_id, "p_expected": expected,
            "p_new": changes, "p_actor": actor}).execute()
    except Exception as exc:
        msg = str(exc)
        if "CONFLICT" in msg:
            return {"ok": False, "errors": ["Another change was saved first. Reload the entry and try again."]}
        return {"ok": False, "errors": [msg[:300]]}
    return {"ok": True, "errors": [], "result": res.data}


def list_sections():
    return (supabase.table("sections").select("id,code").eq("is_active", True)
            .order("code").execute().data or [])


def list_changes(version_id, limit=20):
    return (supabase.table("timetable_changes")
            .select("changed_at,entry_id,changed_by,before_json,after_json")
            .eq("version_id", version_id).order("changed_at", desc=True)
            .limit(limit).execute().data or [])


def list_period_slots():
    rows = (supabase.table("period_slots").select("period_no,start_time,end_time")
            .order("period_no").execute().data or [])
    return {r["period_no"]: f"{str(r['start_time'])[:5]}-{str(r['end_time'])[:5]}" for r in rows}
