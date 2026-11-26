"""Create a new editable draft by copying an existing timetable version."""
from src.database.config import supabase


class DraftError(Exception):
    """A message that is safe to show to the admin."""


def create_draft(admin_id, source_version_id, new_label):
    label = (new_label or "").strip()
    if not label or len(label) > 80:
        raise DraftError("Enter a name for the new draft (1 to 80 characters).")
    try:
        res = supabase.rpc("timetable_create_draft", {
            "p_source_version_id": int(source_version_id),
            "p_label": label,
            "p_actor": str(admin_id),
        }).execute()
    except Exception as exc:
        msg = str(getattr(exc, "message", "") or exc)
        print(f"timetable_create_draft failed: {type(exc).__name__}")
        if "already exists" in msg:
            raise DraftError("A version with that name already exists. Choose another name.") from None
        if "not found" in msg:
            raise DraftError("The source version no longer exists. Reload the page.") from None
        raise DraftError("Could not create the draft. Please try again.") from None
    return res.data
