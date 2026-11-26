"""Photo-style timetable rendering. Pure functions that return HTML strings (no Streamlit).
Every value from the database is HTML-escaped before it goes into markup."""
from html import escape

from src.services.timetable_validator import DAYS, LUNCH_AFTER, TEACHING

DAY_NAMES = {1: "MONDAY", 2: "TUESDAY", 3: "WEDNESDAY", 4: "THURSDAY", 5: "FRIDAY", 6: "SATURDAY"}
DAY_SHORT = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
KIND_TAG = {"theory": "TH", "lab": "LAB", "training": "TRAINING", "activity": "ACTIVITY"}
KIND_BG = {"theory": "#e5e7eb", "lab": "#fed7aa", "training": "#fef08a", "activity": "#bfdbfe"}
LUNCH = "L"
CELL = "border:1px solid #9ca3af;padding:4px 6px;vertical-align:top;font-size:12px;"
HEAD = CELL + "background:#f3f4f6;font-weight:600;text-align:center;"


def _t(value):
    return escape("" if value is None else str(value))


def section_sort_key(code):
    year = 1 if code[:1] in ("P", "C") else int(code[0])
    return (year, code)


def _columns(periods, lunch_after):
    cols = []
    for p in periods:
        cols.append(p)
        if lunch_after and p == lunch_after:
            cols.append(LUNCH)
    return cols


def _block_end_index(cols, idx, end):
    """Index of the first column after a block that starts at cols[idx] and ends before `end`.
    A lunch column belongs to the block only if the block continues past it."""
    j = idx + 1
    while j < len(cols):
        c = cols[j]
        if c == LUNCH:
            nxt = cols[j + 1] if j + 1 < len(cols) else None
            if nxt is None or nxt >= end:
                return j
        elif c >= end:
            return j
        j += 1
    return len(cols)


def _section_cell(e, changed=False):
    tag = KIND_TAG.get(e.kind, e.kind.upper())
    subject = e.subject_name or ""
    if e.subject_code:
        subject = f"{subject} ({e.subject_code})" if subject else e.subject_code
    lines = [("CHANGED: " if changed else "") + tag]
    if subject:
        lines.append(subject)
    if e.faculty_code:
        lines.append(e.faculty_code)
    return "<br>".join(_t(x) for x in lines)


def section_grid_html(entries, slot_times, title="", lunch_after=LUNCH_AFTER, changed_ids=frozenset()):
    """Days as rows, periods as columns, LUNCH after `lunch_after`, like the department photo."""
    periods = sorted(slot_times)
    cols = _columns(periods, lunch_after)
    starts = {(e.weekday, e.period_no): e for e in entries}

    head = [f"<th style='{HEAD}'>DAY</th>"]
    for c in cols:
        if c == LUNCH:
            head.append(f"<th style='{HEAD}'>LUNCH</th>")
        else:
            head.append(f"<th style='{HEAD}'>P{c}<br><span style='font-weight:400'>"
                        f"{_t(slot_times.get(c, ''))}</span></th>")

    rows = []
    for d in DAYS:
        cells = [f"<td style='{HEAD}'>{DAY_NAMES[d]}</td>"]
        idx = 0
        while idx < len(cols):
            c = cols[idx]
            if c == LUNCH:
                cells.append(f"<td style='{CELL}background:#ffffff;text-align:center;font-weight:700;'>LUNCH</td>")
                idx += 1
                continue
            e = starts.get((d, c))
            if e is None:
                cells.append(f"<td style='{CELL}'></td>")
                idx += 1
                continue
            end_idx = _block_end_index(cols, idx, e.period_no + e.block_len)
            span = end_idx - idx
            bg = KIND_BG.get(e.kind, "#ffffff")
            is_changed = e.id in changed_ids
            extra = "box-shadow:inset 0 0 0 3px #ea580c;" if is_changed else ""
            cells.append(f"<td colspan='{span}' style='{CELL}{extra}background:{bg};'>{_section_cell(e, is_changed)}</td>")
            idx = end_idx
        rows.append("<tr>" + "".join(cells) + "</tr>")

    heading = f"<div style='font-weight:700;margin:10px 0 4px;'>{_t(title)}</div>" if title else ""
    return ("<div style='overflow-x:auto;'>" + heading +
            "<table style='border-collapse:collapse;width:100%;min-width:900px;'>"
            f"<thead><tr>{''.join(head)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def all_sections_html(entries, slot_times, lunch_after=LUNCH_AFTER, changed_ids=frozenset()):
    by_section = {}
    for e in entries:
        by_section.setdefault(e.section_code, []).append(e)
    return "".join(
        section_grid_html(by_section[code], slot_times, f"Section {code}", lunch_after, changed_ids)
        for code in sorted(by_section, key=section_sort_key)
    )


def _period_label(e):
    if e.block_len > 1:
        return f"P{e.period_no}-{e.period_no + e.block_len - 1}"
    return f"P{e.period_no}"


def teacher_matrix_html(entries, teachers=()):
    """One row per teacher: their periods for each day, across every section in the draft."""
    per = {}
    for e in entries:
        if e.kind in TEACHING and e.faculty_code:
            per.setdefault(e.faculty_code, {d: [] for d in DAYS})[e.weekday].append(e)
    codes = sorted(set(teachers) | set(per))

    head = [f"<th style='{HEAD}'>TEACHER</th>"]
    head += [f"<th style='{HEAD}'>{DAY_SHORT[d]}</th>" for d in DAYS]
    head.append(f"<th style='{HEAD}'>PERIODS / WEEK</th>")

    rows = []
    for code in codes:
        days = per.get(code, {d: [] for d in DAYS})
        total = 0
        cells = [f"<td style='{CELL}font-weight:700;'>{_t(code)}</td>"]
        for d in DAYS:
            items = sorted(days[d], key=lambda e: e.period_no)
            total += sum(e.block_len for e in items)
            text = "<br>".join(_t(f"{_period_label(e)} {e.subject_code or ''} {e.section_code}".strip())
                               for e in items)
            cells.append(f"<td style='{CELL}'>{text}</td>")
        cells.append(f"<td style='{CELL}text-align:center;font-weight:700;'>{total}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    return ("<div style='overflow-x:auto;'>"
            "<table style='border-collapse:collapse;width:100%;min-width:900px;'>"
            f"<thead><tr>{''.join(head)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")
