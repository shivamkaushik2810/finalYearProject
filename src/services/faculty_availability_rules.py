"""Pure faculty planning rules. No database or Streamlit imports.
Used by the substitution engine (Phase 4) and the admin screens (Phase 5)."""
from datetime import date

from src.services.timetable_validator import TEACHING

LEVELS = ("trained", "primary", "secondary")
DAYS = tuple(range(1, 7))
PERIODS = tuple(range(1, 9))
REASON_MIN, REASON_MAX = 3, 200
MAX_DAILY, MAX_WEEKLY = 8, 48


class PlanningError(ValueError):
    """A rule was broken. The message is safe to show to the user."""


def validate_unavailability(weekday, period, reason, start, until):
    errors = []
    if weekday not in DAYS:
        errors.append("day must be Monday to Saturday")
    if period is not None and period not in PERIODS:
        errors.append("period must be 1 to 8, or empty for the whole day")
    text = (reason or "").strip()
    if not REASON_MIN <= len(text) <= REASON_MAX:
        errors.append(f"the reason must be {REASON_MIN} to {REASON_MAX} characters")
    if not isinstance(start, date):
        errors.append("a start date is required")
    elif until is not None and until < start:
        errors.append("the end date is before the start date")
    return errors


def validate_limits(max_daily, max_weekly):
    errors = []
    if not 0 <= max_daily <= MAX_DAILY:
        errors.append(f"the daily maximum must be 0 to {MAX_DAILY}")
    if not 0 <= max_weekly <= MAX_WEEKLY:
        errors.append(f"the weekly maximum must be 0 to {MAX_WEEKLY}")
    if max_daily > max_weekly:
        errors.append("the daily maximum cannot be more than the weekly maximum")
    return errors


def is_qualified(quals, subject_code):
    row = quals.get(subject_code)
    return bool(row and row.get("is_active") and row.get("level") in LEVELS)


def busy_periods(entries, code, weekday):
    """Periods in which this teacher already teaches on this day, from the timetable."""
    busy = set()
    for e in entries:
        if e.weekday == weekday and e.kind in TEACHING and e.faculty_code == code:
            busy.update(range(e.period_no, e.period_no + e.block_len))
    return busy


def unavailable_periods(rules, weekday, on_date):
    out = set()
    for r in rules:
        if r["weekday"] != weekday or r["effective_from"] > on_date:
            continue
        until = r.get("effective_until")
        if until is not None and until < on_date:
            continue
        if r.get("period_no") is None:
            out.update(PERIODS)
        else:
            out.add(r["period_no"])
    return out


def absent_periods(absences, on_date):
    """Approved absences only. A whole-day absence (no periods) covers every period."""
    out = set()
    for a in absences:
        if a["status"] != "approved" or not a["start_date"] <= on_date <= a["end_date"]:
            continue
        periods = a.get("periods")
        out.update(periods if periods else PERIODS)
    return out


def free_periods(code, weekday, on_date, entries, rules, absences):
    if not code:
        return []
    blocked = (busy_periods(entries, code, weekday)
               | unavailable_periods(rules, weekday, on_date)
               | absent_periods(absences, on_date))
    return [p for p in PERIODS if p not in blocked]


def teaching_load(entries, code, weekday=None):
    total = 0
    for e in entries:
        if e.kind in TEACHING and e.faculty_code == code and (weekday is None or e.weekday == weekday):
            total += e.block_len
    return total


def eligibility_reasons(*, code, subject_code, weekday, period, on_date, entries, quals,
                        rules, absences, limits, teacher_status, extra=1):
    """Empty list means eligible. Every reason is a hard stop; nothing here is a score."""
    reasons = []
    if teacher_status != "approved":
        reasons.append("the teacher account is not approved")
    if not is_qualified(quals, subject_code):
        reasons.append(f"not qualified to teach {subject_code}")
    if not code:
        reasons.append("no timetable code is linked to this teacher")
        return reasons
    if weekday not in DAYS or period not in PERIODS:
        reasons.append("the slot is not a valid day and period")
        return reasons
    if period in busy_periods(entries, code, weekday):
        reasons.append(f"already teaching in period {period}")
    if period in unavailable_periods(rules, weekday, on_date):
        reasons.append("marked unavailable at this time")
    if period in absent_periods(absences, on_date):
        reasons.append("on approved absence at this time")
    if limits is None:
        reasons.append("workload limits are not set")
    else:
        if teaching_load(entries, code, weekday) + extra > limits["max_daily"]:
            reasons.append(f"would exceed the daily limit of {limits['max_daily']} periods")
        if teaching_load(entries, code) + extra > limits["max_weekly"]:
            reasons.append(f"would exceed the weekly limit of {limits['max_weekly']} periods")
    return reasons
