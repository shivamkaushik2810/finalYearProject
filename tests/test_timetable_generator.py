from collections import Counter

from src.services import timetable_generator as g


def needs_demo():
    return [
        g.Need("3D", "CN", "theory", "RM", 4, 1, "R1"),
        g.Need("3D", "MLT", "theory", "VU", 4, 1, "R2"),
        g.Need("3D", "SE", "theory", "PS", 3, 1, "R3"),
        g.Need("3D", "CNL", "lab", "RM", 1, 2, "L1"),
        g.Need("2A", "CN", "theory", "RM", 3, 1, "R4"),
        g.Need("2A", "TH", "theory", "VU", 3, 1, "R5"),
    ]


def test_no_clashes_and_every_block_placed():
    res = g.generate(needs_demo(), seed=3)
    assert g.find_clashes(res.placements) == []
    assert res.unplaced == []
    assert sum(p.block_len for p in res.placements) == sum(n.count * n.block_len for n in needs_demo())


def test_lab_is_two_consecutive_periods_inside_the_day():
    labs = [p for p in g.generate(needs_demo(), seed=3).placements if p.kind == "lab"]
    assert len(labs) == 1 and labs[0].block_len == 2
    assert labs[0].period_no + 1 <= g.LAST_PERIOD


def test_teacher_daily_limit_is_respected():
    needs = [g.Need("3D", f"S{i}", "theory", "RM", 1, 1, f"R{i}") for i in range(7)]
    res = g.generate(needs, seed=5, max_teacher_per_day=2)
    per_day = Counter(p.weekday for p in res.placements)
    assert max(per_day.values()) <= 2


def test_impossible_need_is_reported_not_dropped():
    needs = [g.Need("3D", "X", "theory", "RM", 8, 1, "")]
    res = g.generate(needs, seed=2, max_teacher_per_day=1)
    placed = len(res.placements)
    missing = sum(m for _, m in res.unplaced)
    assert placed + missing == 8
    assert placed <= len(g.DAYS)


def test_different_seeds_give_different_timetables():
    a = g.generate(needs_demo(), seed=1)
    b = g.generate(needs_demo(), seed=2)
    assert g.similarity(a.placements, b.placements) < 1.0


def test_identical_timetable_is_fully_similar():
    a = g.generate(needs_demo(), seed=1)
    assert g.similarity(a.placements, a.placements) == 1.0


def test_generate_varied_avoids_the_previous_timetable():
    prev = g.generate(needs_demo(), seed=1)
    res, sim, ok = g.generate_varied(needs_demo(), previous=prev.placements, max_similarity=0.35)
    assert ok is True
    assert sim <= 0.35
    assert g.find_clashes(res.placements) == []
