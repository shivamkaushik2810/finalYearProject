"""Pure workload report: teaching periods per teacher across all sections and years.
Targets come from the draft itself (equal share) unless a target is given explicitly."""
from src.services.timetable_validator import TEACHING

TOLERANCE_PERIODS = 1


def teaching_periods(entries):
    totals = {}
    for e in entries:
        if e.kind in TEACHING and e.faculty_code:
            totals[e.faculty_code] = totals.get(e.faculty_code, 0) + e.block_len
    return totals


def workload_report(entries, teachers, minutes_per_period=50, target_periods=None):
    teachers = sorted(set(teachers))
    counts = teaching_periods(entries)
    total = sum(counts.values())
    if target_periods is not None:
        target = float(target_periods)
    else:
        target = total / len(teachers) if teachers else 0.0
    rows = []
    for code in sorted(set(teachers) | set(counts)):
        p = counts.get(code, 0)
        if p > target + TOLERANCE_PERIODS:
            status = "over"
        elif p < target - TOLERANCE_PERIODS:
            status = "under"
        else:
            status = "ok"
        rows.append({
            "faculty": code,
            "periods": p,
            "hours": round(p * minutes_per_period / 60, 2),
            "vs_target": round(p - target, 2),
            "status": status,
        })
    return {
        "target_periods": round(target, 2),
        "rows": rows,
        "unlisted": sorted(c for c in counts if c not in teachers),
    }
