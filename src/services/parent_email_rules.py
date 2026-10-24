from src.database.config import supabase

MAX_STUDENTS_PER_PARENT = 4


def _norm(email):
    return (email or "").strip().lower()


def _escape_like(value):
    # '_' and '%' are wildcards in ilike; emails often contain '_'
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_parent_email(student_email, parent_email, student_id=None):
    """Return (ok, message). student_id is None during registration."""
    s = _norm(student_email)
    p = _norm(parent_email)

    if not p or "@" not in p:
        return False, "Enter a valid parent email."
    if s and s == p:
        return False, "Parent email must be different from your own email."

    pattern = _escape_like(p)

    res = supabase.table("students").select("student_id").ilike("email", pattern).execute()
    if [r for r in (res.data or []) if r["student_id"] != student_id]:
        return False, "This email belongs to a student account. Use your parent's own email."

    res = supabase.table("students").select("student_id").ilike("parent_email", pattern).execute()
    linked = [r for r in (res.data or []) if r["student_id"] != student_id]
    if len(linked) >= MAX_STUDENTS_PER_PARENT:
        return False, "This parent email is already linked to too many students. Contact admin."

    return True, ""
