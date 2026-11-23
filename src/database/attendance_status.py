EXCLUDED = ("excused", "cancelled")


def eligible(rows):
    """Rows that count towards attendance.
    Left out: cancelled classes, excused status, and absences excused by an approved leave
    (is_excused = true and not present)."""
    out = []
    for r in rows or []:
        if str(r.get("status") or "").lower() in EXCLUDED:
            continue
        if r.get("is_excused") and not r.get("is_present"):
            continue
        out.append(r)
    return out
