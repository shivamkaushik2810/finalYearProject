"""Single source of truth for attendance thresholds and status labels.
Change the numbers here and every screen follows."""

ATTENDANCE_TARGET = 75   # at or above = Good (on track)
ATTENDANCE_WARN = 50     # at or above = Average, below = At risk


def status_label(pct):
    if pct is None:
        return "No data"
    if pct >= ATTENDANCE_TARGET:
        return "Good"
    if pct >= ATTENDANCE_WARN:
        return "Average"
    return "At risk"


def status_icon(pct):
    if pct is None:
        return "⚪"
    if pct >= ATTENDANCE_TARGET:
        return "🟢"
    if pct >= ATTENDANCE_WARN:
        return "🟡"
    return "🔴"
