"""Read-only timetable analytics. Pure functions: they take classes, changes and substitution rows
and return numbers. They never write to the database. Limits such as the weekly teaching limit
are parameters, so the admin can change them."""
from collections import Counter, defaultdict

from src.services.timetable_validator import DAYS, PERIODS, TEACHING

SLOTS_PER_WEEK = len(DAYS) * len(PERIODS)
DEFAULT_WEEKLY_LIMIT = 20
LOW_ROOM_USE = 30.0


def _span(e):
    return e.block_len or 1


def _cells(e):
    return [(e.weekday, e.period_no + i) for i in range(_span(e))]


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def _covered(entries):
    """(section, weekday, period) for every occupied slot."""
    out = set()
    for e in entries:
        for weekday, period in _cells(e):
            out.add((e.section_code, weekday, period))
    return out


def clash_pairs(entries):
    """Pairs of classes that clash, with the reason. Same rules as the database check."""
    found = []
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if a.weekday != b.weekday:
                continue
            if not (a.period_no < b.period_no + _span(b) and b.period_no < a.period_no + _span(a)):
                continue
            if a.section_code == b.section_code:
                found.append((a.id, b.id, "section"))
            elif a.kind in TEACHING and b.kind in TEACHING and a.faculty_code and a.faculty_code == b.faculty_code:
                found.append((a.id, b.id, "teacher"))
            elif a.room and a.room == b.room:
                found.append((a.id, b.id, "room"))
    return found


def overview(entries):
    teaching = [e for e in entries if e.kind in TEACHING]
    sections = len({e.section_code for e in entries})
    total_slots = max(1, sections) * SLOTS_PER_WEEK
    return {
        "sections": sections,
        "classes": len(entries),
        "periods": sum(_span(e) for e in entries),
        "teachers": len({e.faculty_code for e in teaching if e.faculty_code}),
        "rooms": len({e.room for e in entries if e.room}),
        "unassigned": sum(1 for e in teaching if not e.faculty_code),
        "conflicts": len(clash_pairs(entries)),
        "completion": _pct(len(_covered(entries)), total_slots),
    }


def faculty_workload(entries, weekly_limit=DEFAULT_WEEKLY_LIMIT):
    rows = defaultdict(lambda: {"periods": 0, "classes": 0, "sections": set(), "subjects": Counter()})
    for e in entries:
        if e.kind in TEACHING and e.faculty_code:
            r = rows[e.faculty_code]
            r["periods"] += _span(e)
            r["classes"] += 1
            r["sections"].add(e.section_code)
            r["subjects"][e.subject_code or e.kind] += 1
    out = []
    for code, r in rows.items():
        out.append({
            "teacher": code,
            "periods": r["periods"],
            "classes": r["classes"],
            "sections": len(r["sections"]),
            "free_periods": max(0, SLOTS_PER_WEEK - r["periods"]),
            "overloaded": r["periods"] > weekly_limit,
            "subjects": ", ".join(s for s, _ in r["subjects"].most_common()),
        })
    return sorted(out, key=lambda x: (-x["periods"], x["teacher"]))


def workload_stats(workload):
    if not workload:
        return {"max": 0, "min": 0, "average": 0.0, "overloaded": 0}
    loads = [w["periods"] for w in workload]
    return {"max": max(loads), "min": min(loads), "average": round(sum(loads) / len(loads), 1),
            "overloaded": sum(1 for w in workload if w["overloaded"])}


def room_usage(entries, known_rooms=()):
    """Returns (rooms in use with their load, rooms in known_rooms that are not used at all)."""
    cells, lectures = defaultdict(set), Counter()
    for e in entries:
        if e.room:
            cells[e.room].update(_cells(e))
            lectures[e.room] += 1
    rooms = []
    for room in sorted(cells):
        used = len(cells[room])
        util = _pct(used, SLOTS_PER_WEEK)
        rooms.append({"room": room, "lectures": lectures[room], "periods": used,
                      "utilisation": util, "underused": util < LOW_ROOM_USE})
    empty = sorted(set(known_rooms) - set(cells))
    return rooms, empty


def peak_periods(entries):
    """How many classes run in each period number across the week (all sections)."""
    counts = Counter()
    for _section, _weekday, period in _covered(entries):
        counts[period] += 1
    return dict(sorted(counts.items()))


def section_stats(entries):
    by = defaultdict(list)
    for e in entries:
        by[e.section_code].append(e)
    out = []
    for code in sorted(by):
        items = by[code]
        kinds = Counter(e.kind for e in items)
        cells = set()
        for e in items:
            cells.update(_cells(e))
        per_day = Counter(w for w, _ in cells)
        out.append({
            "section": code,
            "classes": len(items),
            "theory": kinds["theory"],
            "lab": kinds["lab"],
            "training": kinds["training"],
            "activity": kinds["activity"],
            "practical_share": _pct(kinds["lab"], len(items)),
            "periods": len(cells),
            "free_periods": max(0, SLOTS_PER_WEEK - len(cells)),
            "completion": _pct(len(cells), SLOTS_PER_WEEK),
            "daily": dict(sorted(per_day.items())),
        })
    return out


def change_summary(changes):
    """Changes made by admins. The original import is not counted."""
    real = [c for c in changes if c.get("changed_by") != "import"]
    moved = Counter()
    for c in real:
        if c.get("action") in ("update", "swap"):
            src = c.get("before_json") or {}
            moved[src.get("subject_code") or src.get("subject_name") or "(no subject)"] += 1
    return {
        "total": len(real),
        "by_action": dict(Counter(c.get("action") for c in real)),
        "by_user": dict(Counter(c.get("changed_by") for c in real)),
        "most_changed": moved.most_common(5),
    }


def substitution_summary(rows):
    assigned = [r for r in rows if r.get("status") == "assigned"]
    return {
        "total": len(rows),
        "assigned": len(assigned),
        "by_status": dict(Counter(r.get("status") for r in rows)),
        "absent_teachers": Counter(r.get("original_teacher_code") or "?" for r in assigned).most_common(10),
    }
