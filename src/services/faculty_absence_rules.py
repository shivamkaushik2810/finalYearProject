"""Pure rules for faculty absences. No database or Streamlit imports."""
from datetime import date, timedelta

KINDS = ("planned", "emergency", "unplanned")
PERIOD_RANGE = range(1, 9)
MAX_SPAN_DAYS = 30
MAX_BACKDATE_DAYS = 30
REASON_MIN, REASON_MAX = 5, 500


def normalise_periods(periods):
    """None or empty means the whole day. Otherwise a sorted list of distinct period numbers."""
    if periods is None or len(periods) == 0:
        return None
    try:
        return sorted({int(p) for p in periods})
    except (TypeError, ValueError):
        raise ValueError("periods must be whole numbers")


def periods_overlap(a, b):
    if a is None or b is None:
        return True
    return bool(set(a) & set(b))


def dates_overlap(start1, end1, start2, end2):
    return start1 <= end2 and start2 <= end1


def absences_clash(a, b):
    """a and b are dicts with start, end and periods. Mirrors the SQL overlap check."""
    return dates_overlap(a["start"], a["end"], b["start"], b["end"]) and periods_overlap(a["periods"], b["periods"])


def validate_absence(start, end, kind, periods, reason, today, is_admin):
    errors = []
    if kind not in KINDS:
        errors.append(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(start, date) or not isinstance(end, date):
        return errors + ["start and end dates are required"]
    if end < start:
        errors.append("the end date is before the start date")
    elif (end - start).days + 1 > MAX_SPAN_DAYS:
        errors.append(f"an absence can cover at most {MAX_SPAN_DAYS} days")
    if start < today - timedelta(days=MAX_BACKDATE_DAYS):
        errors.append(f"an absence cannot start more than {MAX_BACKDATE_DAYS} days ago")
    if kind == "planned" and start < today and not is_admin:
        errors.append("a planned absence must start today or later")
    if kind != "planned" and not is_admin:
        errors.append("only an administrator can record emergency or unplanned absences")
    if periods is not None and any(p not in PERIOD_RANGE for p in periods):
        errors.append("periods must be 1 to 8")
    text = (reason or "").strip()
    if not REASON_MIN <= len(text) <= REASON_MAX:
        errors.append(f"the reason must be {REASON_MIN} to {REASON_MAX} characters")
    return errors
