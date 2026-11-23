"""Single source of truth for attendance percentages.
Cancelled classes never count, excused absences leave the denominator,
a missing value is never treated as zero, and one class counts once."""
from datetime import date

from src.database.attendance_status import eligible


def _in_window(row, start, end):
    if start is None and end is None:
        return True
    ts = str(row.get("timestamp") or "")[:10]
    try:
        day = date.fromisoformat(ts)
    except ValueError:
        return False
    if start is not None and day < start:
        return False
    if end is not None and day > end:
        return False
    return True


def summarize(logs, start=None, end=None):
    """Return {'present', 'total', 'absent', 'pct'}. pct is None when nothing is counted."""
    rows = [r for r in eligible(list(logs or [])) if _in_window(r, start, end)]
    seen = {}
    for r in rows:
        key = (r.get("subject_id"), str(r.get("timestamp")))
        seen[key] = seen.get(key, False) or (r.get("is_present") is True)
    total = len(seen)
    present = sum(1 for v in seen.values() if v)
    pct = round(present / total * 100, 1) if total else None
    return {"present": present, "total": total, "absent": total - present, "pct": pct}


def scope_label(start=None, end=None):
    if start is None and end is None:
        return "all classes"
    s = start.strftime("%d %b") if start else "start"
    e = end.strftime("%d %b %Y") if end else "today"
    return f"{s} to {e}"


def week_bounds(day):
    """Monday to Sunday containing the given date."""
    monday = date.fromordinal(day.toordinal() - day.weekday())
    return monday, date.fromordinal(monday.toordinal() + 6)
