"""Parse and check a marks CSV before anything is saved. Pure: no database, no Streamlit.
Blank marks are skipped, never saved as zero. Any other problem rejects that row, with its line number."""
import csv
import io
import math
from datetime import date

MAX_BYTES = 1024 * 1024
MAX_ROWS = 2000
MAX_MAX = 1000
EXAM_TYPES = ("Quiz", "Assignment", "Practical", "Internal", "Mid Term", "End Term")
REQUIRED = ("roll_no", "exam_type", "marks_obtained", "max_marks")
TEMPLATE = ("roll_no,exam_type,marks_obtained,max_marks,remarks,exam_date\n"
            "A01,Mid Term,40,50,,2026-09-01\n"
            "A02,Mid Term,,50,Absent from exam,2026-09-01\n")


def _num(text):
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def parse_marks_csv(raw, roll_to_student, exam_types=EXAM_TYPES):
    """roll_to_student: {roll_no: student_id}, or None when two students share a roll number.
    Returns (rows, errors, skipped_blank)."""
    if not raw:
        return [], ["The file is empty."], 0
    if len(raw) > MAX_BYTES:
        return [], ["The file is larger than 1 MB."], 0
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["The file must be saved as UTF-8 CSV."], 0
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["The file has no header row."], 0
    headers = {(h or "").strip().lower() for h in reader.fieldnames}
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        return [], ["Missing column(s): " + ", ".join(missing)], 0

    exam_lookup = {e.lower(): e for e in exam_types}
    rows, errors, seen = [], [], set()
    skipped = 0
    for n, raw_rec in enumerate(reader, start=2):
        if len(rows) + skipped + len(errors) >= MAX_ROWS:
            errors.append(f"More than {MAX_ROWS} rows. Split the file.")
            break
        rec = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_rec.items() if k}
        if not any(rec.values()):
            continue

        problems = []
        roll = rec.get("roll_no", "")
        sid = roll_to_student.get(roll) if roll else None
        if not roll:
            problems.append("roll number is blank")
        elif roll not in roll_to_student:
            problems.append(f"roll number {roll} is not enrolled in this subject")
        elif sid is None:
            problems.append(f"roll number {roll} is shared by two students")

        exam = exam_lookup.get(rec.get("exam_type", "").lower())
        if exam is None:
            problems.append("exam_type must be one of: " + ", ".join(exam_types))

        mx = _num(rec.get("max_marks", ""))
        if mx is None or not (0 < mx <= MAX_MAX):
            problems.append(f"max_marks must be a number from 0 to {MAX_MAX}")

        obt_text = rec.get("marks_obtained", "")
        blank_marks = obt_text == ""
        obt = None
        if not blank_marks:
            obt = _num(obt_text)
            if obt is None or mx is None or not (0 <= obt <= mx):
                problems.append("marks_obtained must be a number from 0 to max_marks")

        if problems:
            errors.append(f"Line {n}: " + "; ".join(problems))
            continue
        if blank_marks:
            skipped += 1
            continue

        key = (sid, exam)
        if key in seen:
            errors.append(f"Line {n}: {roll} already has a {exam} mark in this file")
            continue

        exam_date = rec.get("exam_date", "")
        if exam_date:
            try:
                exam_date = date.fromisoformat(exam_date).isoformat()
            except ValueError:
                errors.append(f"Line {n}: exam_date must look like 2026-09-01")
                continue
        else:
            exam_date = None

        remarks = rec.get("remarks", "")
        if len(remarks) > 200:
            errors.append(f"Line {n}: remarks are longer than 200 characters")
            continue

        seen.add(key)
        rows.append({"line": n, "student_id": sid, "roll_no": roll, "exam_type": exam,
                     "marks_obtained": obt, "max_marks": mx, "remarks": remarks or None,
                     "exam_date": exam_date})
    return rows, errors, skipped
