"""Substitution analytics (Phase 8). Pure functions over plain rows. No database or Streamlit imports.

Rows: faculty_substitutions rows (id, substitution_date, status, substitute_name,
original_teacher_code, subject_code, reasons, created_at).
Events: faculty_substitution_events rows (substitution_id, action, at)."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone

ASSIGNING_ACTIONS = ("confirm", "override")


def pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _instant(value):
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def summary(rows):
    total = len(rows)
    assigned = sum(1 for r in rows if r["status"] == "assigned")
    proposed = sum(1 for r in rows if r["status"] == "proposed")
    unassigned = sum(1 for r in rows if r["status"] == "unassigned")
    return {"total": total, "assigned": assigned, "proposed": proposed, "unassigned": unassigned,
            "assigned_pct": pct(assigned, total), "unassigned_pct": pct(unassigned, total)}


def _buckets(rows, keyfn):
    out = {}
    for r in rows:
        key = keyfn(_date(r["substitution_date"]))
        b = out.setdefault(key, {"period": key, "total": 0, "assigned": 0, "unassigned": 0})
        b["total"] += 1
        if r["status"] == "assigned":
            b["assigned"] += 1
        elif r["status"] == "unassigned":
            b["unassigned"] += 1
    return [out[k] for k in sorted(out)]


def by_week(rows):
    return _buckets(rows, lambda d: (d - timedelta(days=d.weekday())).isoformat())


def by_month(rows):
    return _buckets(rows, lambda d: d.strftime("%Y-%m"))


def top_counts(values, k=5):
    return [{"name": n, "count": c} for n, c in Counter(v for v in values if v).most_common(k)]


def most_absent(rows, k=5):
    return top_counts((r["original_teacher_code"] for r in rows), k)


def most_used_substitutes(rows, k=5):
    return top_counts((r.get("substitute_name") for r in rows if r["status"] == "assigned"), k)


def substitute_workload(rows):
    return top_counts((r.get("substitute_name") for r in rows if r["status"] == "assigned"), k=None)


def by_subject(rows):
    return top_counts((r["subject_code"] for r in rows), k=None)


def by_department(rows, department_of):
    """Absences grouped by the absent teacher's department. Teachers without a recorded
    department are counted as 'Unknown' until departments are entered."""
    return top_counts((department_of.get(r["original_teacher_code"], "Unknown") for r in rows), k=None)


def unassigned_reasons(rows, k=5):
    return top_counts((r.get("reasons") for r in rows if r["status"] == "unassigned"), k)


def decision_rates(events):
    count = Counter(e["action"] for e in events)
    accepted, declined = count["accept"], count["decline"]
    confirmed, overridden, rejected = count["confirm"], count["override"], count["reject"]
    decided = confirmed + overridden + rejected
    return {"accepted": accepted, "declined": declined, "confirmed": confirmed,
            "overridden": overridden, "rejected": rejected,
            "acceptance_rate": pct(accepted, accepted + declined),
            "rejection_rate": pct(rejected, decided)}


def assignment_speed(rows, events):
    """Minutes from a class being planned to its first confirm or override. Only substitutions
    with such an event are measured; 'coverage_pct' says how many that is."""
    created = {r["id"]: _instant(r["created_at"]) for r in rows if r.get("created_at")}
    first = {}
    for e in sorted(events, key=lambda e: _instant(e["at"])):
        if e["action"] in ASSIGNING_ACTIONS and e["substitution_id"] in created:
            first.setdefault(e["substitution_id"], _instant(e["at"]))
    minutes = [(first[i] - created[i]).total_seconds() / 60
               for i in first if first[i] >= created[i]]
    return {"measured": len(minutes), "of": len(rows), "coverage_pct": pct(len(minutes), len(rows)),
            "avg_minutes": round(sum(minutes) / len(minutes), 1) if minutes else None}
