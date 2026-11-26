"""Automatic DRAFT timetable generator. Pure Python: no database, no Streamlit.

Places each section's weekly classes into the day and period grid so that no section, teacher or
room is used twice in one period, and labs get two consecutive periods. Nothing is saved here.
The caller writes the result into a NEW draft version, where the database checks clashes again.

Variety: each run uses a different seed. A run is rejected if it is too similar to the previous
timetable (same subject and teacher in the same slot)."""
import random
from collections import Counter
from dataclasses import dataclass, field

from src.services.timetable_validator import DAYS, PERIODS

LAST_PERIOD = max(PERIODS)


@dataclass(frozen=True)
class Need:
    section: str
    subject_code: str
    kind: str
    teacher: str
    count: int
    block_len: int
    room: str = ""


@dataclass(frozen=True)
class Placement:
    section: str
    weekday: int
    period_no: int
    block_len: int
    subject_code: str
    kind: str
    teacher: str
    room: str


@dataclass
class Result:
    placements: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)


def _cells(weekday, period, length):
    return [(weekday, period + i) for i in range(length)]


def generate(needs, seed, max_teacher_per_day=6):
    rng = random.Random(seed)
    section_busy, teacher_busy, room_busy = set(), set(), set()
    teacher_day = Counter()
    subject_day = Counter()
    result = Result()

    for need in sorted(needs, key=lambda n: (-n.block_len, n.section, n.subject_code)):
        missing = 0
        for _ in range(need.count):
            options = [(d, p) for d in DAYS for p in PERIODS
                       if p + need.block_len - 1 <= LAST_PERIOD]
            rng.shuffle(options)
            options.sort(key=lambda dp: subject_day[(need.section, need.subject_code, dp[0])])
            chosen = None
            for d, p in options:
                cells = _cells(d, p, need.block_len)
                if any((need.section, d, q) in section_busy for _, q in cells):
                    continue
                if need.teacher and any((need.teacher, d, q) in teacher_busy for _, q in cells):
                    continue
                if need.teacher and teacher_day[(need.teacher, d)] + need.block_len > max_teacher_per_day:
                    continue
                if need.room and any((need.room, d, q) in room_busy for _, q in cells):
                    continue
                chosen = (d, p, cells)
                break
            if chosen is None:
                missing += 1
                continue
            d, p, cells = chosen
            for _, q in cells:
                section_busy.add((need.section, d, q))
                if need.teacher:
                    teacher_busy.add((need.teacher, d, q))
                if need.room:
                    room_busy.add((need.room, d, q))
            if need.teacher:
                teacher_day[(need.teacher, d)] += need.block_len
            subject_day[(need.section, need.subject_code, d)] += 1
            result.placements.append(Placement(need.section, d, p, need.block_len, need.subject_code,
                                               need.kind, need.teacher, need.room))
        if missing:
            result.unplaced.append((need, missing))
    return result


def find_clashes(placements):
    seen, problems = set(), []
    for p in placements:
        for _, q in _cells(p.weekday, p.period_no, p.block_len):
            for tag, value in (("section", p.section), ("teacher", p.teacher), ("room", p.room)):
                if not value:
                    continue
                key = (tag, value, p.weekday, q)
                if key in seen:
                    problems.append(key)
                seen.add(key)
    return problems


def similarity(a, b):
    """Share of the slots of timetable a that have the same subject and teacher in timetable b."""
    def slots(ps):
        m = {}
        for p in ps:
            for _, q in _cells(p.weekday, p.period_no, p.block_len):
                m[(p.section, p.weekday, q)] = (p.subject_code, p.teacher)
        return m
    ma, mb = slots(a), slots(b)
    if not ma:
        return 0.0
    same = sum(1 for k, v in ma.items() if mb.get(k) == v)
    return round(same / len(ma), 3)


def generate_varied(needs, previous=None, max_similarity=0.35, tries=25, base_seed=1):
    """Try several seeds. Returns (result, similarity_to_previous, meets_variation).
    Prefers a run that is different enough and places every class."""
    best = None
    for t in range(tries):
        res = generate(needs, seed=base_seed + t)
        sim = similarity(res.placements, previous) if previous else 0.0
        missing = sum(m for _, m in res.unplaced)
        ok = sim <= max_similarity
        key = (not ok, missing, sim)
        if best is None or key < best[0]:
            best = (key, res, sim)
        if ok and missing == 0:
            break
    _, res, sim = best
    return res, sim, sim <= max_similarity
