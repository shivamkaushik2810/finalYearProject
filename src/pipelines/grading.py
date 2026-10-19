# (min percent, grade, grade points)
_SCALE = [(90, "O", 10), (80, "A+", 9), (70, "A", 8), (60, "B+", 7),
          (50, "B", 6), (40, "C", 5), (0, "F", 0)]

GRADE_ORDER = [g for _, g, _ in _SCALE]


def grade_for(pct):
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return "-"
    for floor, grade, _ in _SCALE:
        if p >= floor:
            return grade
    return "F"


def grade_points(pct):
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return 0
    for floor, _, pts in _SCALE:
        if p >= floor:
            return pts
    return 0
