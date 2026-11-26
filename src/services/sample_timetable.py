"""Sample section timetable builder. SAMPLE DATA ONLY.

Places one section's classes into the 6-day, 8-period grid using the same validator as the
admin editor. Deterministic and all-or-nothing. Pure: no database access.
"""
from src.services.timetable_validator import DAYS, LUNCH_AFTER, PERIODS, Entry, validate

SAMPLE_SECTION = "3C"
SAMPLE_ROOM = "SAMPLE"
CODE_PREFIX = "S"
TITLES = {"Prof", "Dr", "Mr", "Ms", "Mrs"}

# Weekly load per subject. ASSUMPTIONS, not college data.
# (subject_code, subject_name, kind, blocks_per_week, block_len, faculty_name)
CATALOGUE = [
    ("BCS501", "Database Management System", "theory", 3, 1, "Prof. Rohit Sharma"),
    ("BCS502", "Web Technology", "theory", 3, 1, "Prof. Shivam Verma"),
    ("BCS503", "Design and Analysis of Algorithm", "theory", 3, 1, "Dr. Anjali Gupta"),
    ("BCS052", "Data Analytics", "theory", 2, 1, "Dr. Saurabh Jain"),
    ("BNC501", "Constitution of India", "theory", 1, 1, "Mr. Deepak Kumar"),
    ("BCS551", "Database Management System Lab", "lab", 1, 2, "Prof. Rohit Sharma"),
    ("BCS552", "Web Technology Lab", "lab", 1, 2, "Prof. Shivam Verma"),
    ("BCS553", "Design and Analysis of Algorithm Lab", "lab", 1, 2, "Dr. Anjali Gupta"),
]


def sample_code(name):
    """'Prof. Rohit Sharma' -> 'SRS'. Never a real initial code, because of the prefix."""
    words = [w for w in name.replace(".", " ").split() if w not in TITLES]
    return CODE_PREFIX + words[0][0].upper() + words[-1][0].upper()


def sample_faculty_codes(catalogue=CATALOGUE, real_codes=frozenset()):
    codes = {}
    for row in catalogue:
        name = row[-1]
        codes.setdefault(name, sample_code(name))
    if len(set(codes.values())) != len(codes):
        raise ValueError("sample faculty codes collide with each other")
    clash = set(codes.values()) & set(real_codes)
    if clash:
        raise ValueError(f"sample faculty codes collide with real codes: {sorted(clash)}")
    return codes


def crosses_lunch(start, block_len):
    block = range(start, start + block_len)
    return any(p == LUNCH_AFTER and p + 1 in block for p in block)


def expand(catalogue=CATALOGUE):
    jobs = []
    for subject, name, kind, count, block, faculty in catalogue:
        for n in range(count):
            jobs.append({"subject_code": subject, "subject_name": name, "kind": kind,
                         "block_len": block, "faculty_name": faculty, "n": n})
    # Labs first (longest blocks are the hardest to place), then by code and occurrence.
    jobs.sort(key=lambda j: (-j["block_len"], j["subject_code"], j["n"]))
    return jobs


def _best_spot(job, faculty_code, section, placed):
    best = None
    for day in DAYS:
        same_day = sum(1 for e in placed if e.weekday == day and e.subject_code == job["subject_code"])
        for start in PERIODS:
            if start + job["block_len"] - 1 > max(PERIODS):
                continue
            if crosses_lunch(start, job["block_len"]):
                continue
            entry = Entry(id=None, section_id=0, section_code=section, weekday=day, period_no=start,
                          block_len=job["block_len"], kind=job["kind"], subject_code=job["subject_code"],
                          subject_name=job["subject_name"], faculty_code=faculty_code, room=SAMPLE_ROOM)
            if validate(entry, placed):
                continue
            key = (same_day, day, start)
            if best is None or key < best[0]:
                best = (key, entry)
    return None if best is None else best[1]


def build(section=SAMPLE_SECTION, catalogue=CATALOGUE, real_codes=frozenset()):
    codes = sample_faculty_codes(catalogue, real_codes)
    placed, unplaced = [], []
    for job in expand(catalogue):
        spot = _best_spot(job, codes[job["faculty_name"]], section, placed)
        if spot is None:
            unplaced.append({k: job[k] for k in ("subject_code", "faculty_name", "n", "block_len")})
        else:
            placed.append(spot)
    return {"entries": placed, "unplaced": unplaced, "faculty_codes": codes}


def to_csv_rows(result, section=SAMPLE_SECTION):
    rows = []
    for e in sorted(result["entries"], key=lambda e: (e.weekday, e.period_no)):
        rows.append({"section_code": section, "weekday": e.weekday, "period_no": e.period_no,
                     "kind": e.kind, "subject_code": e.subject_code, "subject_name": e.subject_name,
                     "faculty_code": e.faculty_code, "room": e.room, "block_len": e.block_len})
    return rows
