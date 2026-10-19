EXCLUDED = ("excused", "cancelled")


def eligible(rows):
    """Rows that count towards attendance: cancelled classes and excused absences are left out."""
    return [r for r in (rows or []) if str(r.get("status") or "").lower() not in EXCLUDED]
