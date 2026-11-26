"""Pure timetable rules for the admin editor. No database or Streamlit imports.

Day numbers: 1 = Monday ... 6 = Saturday. Period numbers: 1 to 8.
Defaults match the confirmed configuration and can be overridden per call.
"""
from dataclasses import dataclass

TEACHING = ("theory", "lab", "training")
KINDS = ("theory", "lab", "training", "activity")
DAYS = tuple(range(1, 7))
PERIODS = tuple(range(1, 9))
MAX_BLOCK = 4
MAX_CONSECUTIVE = 3
LUNCH_AFTER = 5


@dataclass(frozen=True)
class Entry:
    id: int | None
    section_id: int
    section_code: str
    weekday: int
    period_no: int
    block_len: int
    kind: str
    subject_code: str | None = None
    subject_name: str | None = None
    faculty_code: str | None = None
    room: str | None = None

    def periods(self):
        return range(self.period_no, self.period_no + self.block_len)

    def is_teaching(self):
        return self.kind in TEACHING


def check_shape(e, days=DAYS, periods=PERIODS, max_block=MAX_BLOCK):
    errs = []
    if e.weekday not in days:
        errs.append("day must be Monday to Saturday")
    if e.period_no not in periods:
        errs.append(f"period must be 1 to {max(periods)}")
    if not 1 <= e.block_len <= max_block:
        errs.append(f"block length must be 1 to {max_block} periods")
    elif e.period_no + e.block_len - 1 > max(periods):
        errs.append("block runs past the last period of the day")
    if e.kind not in KINDS:
        errs.append(f"unknown kind '{e.kind}'")
    if e.is_teaching():
        if not e.subject_code:
            errs.append("a teaching entry needs a subject")
        if not e.faculty_code:
            errs.append("a teaching entry needs a faculty member")
    return errs


def check_clashes(e, others):
    """others must NOT contain the entry being edited (the service removes it)."""
    errs = []
    for o in others:
        if e.id is not None and o.id == e.id:
            continue
        if o.weekday != e.weekday:
            continue
        common = sorted(set(o.periods()) & set(e.periods()))
        if not common:
            continue
        p = common[0]
        if o.section_id == e.section_id:
            errs.append(f"section {e.section_code} is already booked in period {p} "
                        f"by {o.subject_code or o.subject_name}")
        if e.is_teaching() and o.is_teaching() and e.faculty_code and o.faculty_code == e.faculty_code:
            errs.append(f"faculty {e.faculty_code} is already teaching in period {p} ({o.section_code})")
        if e.room and o.room == e.room:
            errs.append(f"room {e.room} is already booked in period {p} ({o.section_code})")
    return errs


def check_consecutive(e, others, max_consecutive=MAX_CONSECUTIVE, lunch_after=LUNCH_AFTER):
    """Flags a run of teaching periods for the faculty member that includes the candidate
    and is longer than the limit. A lunch break always ends a run."""
    if not e.is_teaching() or not e.faculty_code:
        return []
    busy = set(e.periods())
    for o in others:
        if o.weekday == e.weekday and o.is_teaching() and o.faculty_code == e.faculty_code:
            busy |= set(o.periods())
    runs, run = [], []
    for p in sorted(busy):
        if run and (p != run[-1] + 1 or run[-1] == lunch_after):
            runs.append(run)
            run = []
        run.append(p)
    if run:
        runs.append(run)
    errs = []
    for r in runs:
        if len(r) > max_consecutive and set(r) & set(e.periods()):
            errs.append(f"{e.faculty_code} would teach {len(r)} periods in a row on day {e.weekday} "
                        f"(periods {r[0]} to {r[-1]}); the limit is {max_consecutive}")
    return errs


def validate(e, others, max_consecutive=MAX_CONSECUTIVE, lunch_after=LUNCH_AFTER):
    shape = check_shape(e)
    if shape:
        return shape
    return check_clashes(e, others) + check_consecutive(e, others, max_consecutive, lunch_after)
