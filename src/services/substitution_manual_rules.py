"""Pure rules for manual substitution changes. No database or Streamlit imports."""

MAX_CONSECUTIVE = 3
LUNCH_AFTER = 5
REASON_MIN = 5
REASON_MAX = 300


def run_ok(periods, limit=MAX_CONSECUTIVE, lunch_after=LUNCH_AFTER):
    """True if no run of consecutive periods is longer than limit. A lunch break ends a run."""
    prev = None
    run = 0
    for p in sorted(set(periods)):
        if prev is not None and p == prev + 1 and prev != lunch_after:
            run += 1
        else:
            run = 1
        if run > limit:
            return False
        prev = p
    return True


def validate_reason(reason):
    text = (reason or "").strip()
    if not REASON_MIN <= len(text) <= REASON_MAX:
        return f"the reason must be {REASON_MIN} to {REASON_MAX} characters"
    return None
