"""Section export for administrators: one ZIP with attendance, marks and defaulters.
Reads through the same admin-checked functions as the analytics screens. Excused and cancelled classes
are left out (as elsewhere), missing or unverified marks are not counted as zero, and text cells are
protected against spreadsheet formula injection."""
import datetime as dt
import io
import re
import zipfile

import pandas as pd

from src.analytics.access import require_admin
from src.database import analytics_db as adb
from src.database.attendance_status import eligible
from src.services.pure_logic import csv_safe
from src.services.report_export import df_pdf
from src.services.thresholds import ATTENDANCE_TARGET, status_label

MAX_STUDENTS = 300
ATT_COLS = ["Roll No", "Name", "Subject", "Present", "Classes", "Attendance %", "Status"]
MARK_COLS = ["Roll No", "Name", "Subject", "Exam", "Marks", "Max", "Percent"]
DEF_COLS = ["Roll No", "Name", "Classes", "Attendance %"]


def _pct(part, total):
    return round(part / total * 100, 1) if total else None


def _safe(value):
    return csv_safe("" if value is None else str(value))


def _csv(rows, cols):
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode("utf-8")


def build_section_export(section_key, today=None):
    require_admin()
    today = today or dt.date.today()
    students = adb.get_students(section_key)[:MAX_STUDENTS]
    att_rows, mark_rows, defaulters = [], [], []

    for s in students:
        sid = s["student_id"]
        roll, name = _safe(s.get("roll_no")), _safe(s.get("name"))

        by_sub = {}
        for r in eligible(adb.get_attendance(section_key, sid)):
            sub = _safe((r.get("subjects") or {}).get("name") or "Unknown")
            cell = by_sub.setdefault(sub, [0, 0])
            cell[1] += 1
            cell[0] += 1 if r.get("is_present") else 0

        tot_p = tot_t = 0
        for sub, (p, t) in sorted(by_sub.items()):
            pct = _pct(p, t)
            att_rows.append([roll, name, sub, p, t, pct, status_label(pct)])
            tot_p += p
            tot_t += t
        overall = _pct(tot_p, tot_t)
        if overall is not None and overall < ATTENDANCE_TARGET:
            defaulters.append([roll, name, tot_t, overall])

        for m in adb.get_marks(section_key, sid):
            if m.get("marks_obtained") is None or str(m.get("entry_status") or "").lower() == "unverified":
                continue
            got = float(m["marks_obtained"])
            mx = float(m.get("max_marks") or 0)
            sub = _safe((m.get("subjects") or {}).get("name") or "Unknown")
            mark_rows.append([roll, name, sub, _safe(m.get("exam_type")), got, mx, _pct(got, mx)])

    defaulter_df = pd.DataFrame(defaulters, columns=DEF_COLS)
    readme = (
        f"SnapClass section export: Section {section_key}\n"
        f"Generated: {today:%d %B %Y}\n"
        f"Students included: {len(students)}" + (f" (first {MAX_STUDENTS} only)" if len(students) >= MAX_STUDENTS else "") + "\n"
        f"Attendance target: {ATTENDANCE_TARGET}%\n\n"
        "Notes:\n"
        "- Excused and cancelled classes are not counted.\n"
        "- A missing mark is left out, never counted as zero.\n"
        "- Unverified zero scores are left out until a teacher confirms them.\n"
        "- This file contains personal data. Store and share it under your data policy.\n"
    )
    files = {
        "attendance_by_subject.csv": _csv(att_rows, ATT_COLS),
        "marks.csv": _csv(mark_rows, MARK_COLS),
        "defaulters.csv": _csv(defaulters, DEF_COLS),
        "defaulters.pdf": df_pdf(defaulter_df, f"Defaulters - Section {section_key}",
                                 f"Overall attendance below {ATTENDANCE_TARGET}%. Generated {today:%d %b %Y}"),
        "README.txt": readme.encode("utf-8"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)

    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(section_key)) or "section"
    info = {"students": len(students), "attendance_rows": len(att_rows)}
    return buf.getvalue(), f"section_{safe_key}_{today:%Y%m%d}.zip", info
