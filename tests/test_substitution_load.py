"""Phase 9 load check for the planner. Pure: no database.
A realistic week: 60 teachers, 20 sections, 6 days, 8 periods. Five teachers are absent on one day.
The planner must finish inside the limit, and must never give one teacher two classes in a period."""
import time
from datetime import date

from src.services.substitution_scoring import DEFAULT_WEIGHTS, plan_day
from src.services.timetable_validator import Entry

TEACHERS = 60
SECTIONS = 20
ABSENT = 5
LIMIT_SECONDS = 5.0
DAY = date(2026, 11, 25)


def _codes():
    return [f"T{i:02d}" for i in range(TEACHERS)]


def _entries():
    codes = _codes()
    out = []
    for s in range(SECTIONS):
        for d in range(1, 7):
            for p in range(1, 9):
                code = codes[(s * 8 + p + d * 3) % TEACHERS]
                out.append(Entry(id=len(out) + 1, section_id=s, section_code=f"S{s:02d}", weekday=d,
                                 period_no=p, block_len=1, kind="theory", subject_code="BCS 603",
                                 subject_name="CN", faculty_code=code, room=f"R{s}"))
    return out


def _pool():
    return {c: {"code": c, "teacher_id": c, "status": "approved", "department": None,
                "quals": {"BCS 603": {"level": "primary", "is_active": True}},
                "rules": [], "absences": [], "limits": {"max_daily": 6, "max_weekly": 20},
                "previous_sections": set(), "preference": None} for c in _codes()}


def _slots(entries, absent):
    return [{"section_code": e.section_code, "subject_code": e.subject_code, "kind": e.kind,
             "weekday": e.weekday, "period": e.period_no, "room": e.room,
             "absent_code": e.faculty_code, "department": None,
             "absent_codes": set(absent)}
            for e in entries if e.weekday == 3 and e.faculty_code in absent]


def test_planner_finishes_a_realistic_day_within_the_limit():
    entries = _entries()
    absent = set(_codes()[:ABSENT])
    slots = _slots(entries, absent)
    started = time.perf_counter()
    decisions = plan_day(slots, _pool(), entries, dict(DEFAULT_WEIGHTS), DAY)
    elapsed = time.perf_counter() - started
    print(f"\nplanned {len(decisions)} classes in {elapsed:.2f}s")
    assert len(decisions) == len(slots) > 0
    assert elapsed < LIMIT_SECONDS


def test_no_teacher_is_given_two_classes_in_one_period():
    entries = _entries()
    absent = set(_codes()[:ABSENT])
    decisions = plan_day(_slots(entries, absent), _pool(), entries, dict(DEFAULT_WEIGHTS), DAY)
    seen = set()
    for d in decisions:
        if d["status"] == "assigned":
            key = (d["substitute_code"], d["period"])
            assert key not in seen, key
            seen.add(key)
            assert d["substitute_code"] not in absent


def test_planning_is_deterministic_at_scale():
    entries = _entries()
    absent = set(_codes()[:ABSENT])
    a = plan_day(_slots(entries, absent), _pool(), entries, dict(DEFAULT_WEIGHTS), DAY)
    b = plan_day(_slots(entries, absent), _pool(), entries, dict(DEFAULT_WEIGHTS), DAY)
    assert a == b
