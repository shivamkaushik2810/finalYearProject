from datetime import datetime, timedelta, date
from html import escape as _html_escape
import html as _html
from src.database.config import supabase
from src.database.db import (
    get_all_enrolled_students_with_parents,
    get_subjects_for_student,
    get_weekly_attendance,
    save_weekly_report
)
from src.services.email_service import _send
from src.services.thresholds import ATTENDANCE_TARGET, ATTENDANCE_WARN
from src.services import email_templates as T


def _esc(v):
    """HTML-escape a possibly-None value for safe use in email HTML."""
    return "" if v is None else _html_escape(str(v))


def _fmt_date(d):
    if isinstance(d, str):
        d = datetime.fromisoformat(d).date()
    return d.strftime("%d %B %Y")


def send_weekly_parent_email(
    parent_name, parent_email,
    student_name, roll_no, section,
    subject_reports, week_start, week_end
):
    """Send weekly attendance report to parent (shared SnapClass email template)."""
    week_start_str = _fmt_date(week_start)
    week_end_str = _fmt_date(week_end)
    parent_name = parent_name or "Parent"

    total = sum(r['total'] for r in subject_reports)
    present = sum(r['attended'] for r in subject_reports)
    overall = round(present / total * 100, 1) if total > 0 else 0
    tone = "good" if overall >= ATTENDANCE_TARGET else "bad" if overall < ATTENDANCE_WARN else "avg"
    overall_label = "Good" if overall >= ATTENDANCE_TARGET else "Needs Improvement" if overall < ATTENDANCE_WARN else "Average"

    def status(p):
        return ("Good", "#27500A") if p >= ATTENDANCE_TARGET else ("At Risk", "#791F1F") if p < ATTENDANCE_WARN else ("Average", "#633806")

    rows, rows_plain = [], ""
    for r in subject_reports:
        label, color = status(r['attendance_pct'])
        rows.append([(r['subject_name'], None), (f"{r['attended']}/{r['total']}", None),
                     (f"{r['attendance_pct']}%", color), (label, color)])
        rows_plain += f"  {r['subject_name']}: {r['attended']}/{r['total']} ({r['attendance_pct']}%) - {label}\n"

    table = (T.data_table(["Subject", "Classes", "Percentage", "Status"], rows) if rows
             else T.paragraph("No classes this week."))
    body = (
        '<p style="color:#334155;font-size:14px;margin:0 0 12px;">Dear '
        f'<strong>{T.esc(parent_name)}</strong>, here is the weekly attendance report for your ward.</p>'
        + T.info_table([("Student", student_name), ("Roll no.", roll_no or "N/A"),
                        ("Section", section or "N/A"), ("Week", f"{week_start_str} to {week_end_str}")])
        + table
        + T.stat_boxes([(present, "Present", "good"), (total - present, "Absent", "bad"),
                        (f"{overall}%", overall_label, tone)])
        + (T.notice(f"Action Required: Attendance is below {ATTENDANCE_TARGET}%. Please ensure regular attendance "
                    "to avoid academic consequences.") if overall < ATTENDANCE_TARGET else "")
    )
    html = T.shell("Weekly attendance report", "Weekly report", body,
                   "This is an automated weekly report from SnapClass. "
                   "Reports are sent every Monday for the previous week.")
    plain = (f"Dear {parent_name},\n\nWeekly Attendance Report for {student_name}\n"
             f"Week: {week_start_str} to {week_end_str}\nRoll No: {roll_no or 'N/A'} | Section: {section or 'N/A'}\n\n"
             f"Subject-wise Attendance:\n{rows_plain}\n"
             f"Overall Attendance: {present}/{total} ({overall}%) - {overall_label}\n\n"
             "This is an automated weekly report from SnapClass.\n")

    _send(
        parent_email,
        f"📊 Weekly Attendance Report — {student_name} | {week_start_str} to {week_end_str}",
        html, plain
    )


def _already_reported(student_id, week_start):
    """True if a weekly report row already exists for this student+week.
    Raises on DB error so the caller fails closed (no duplicate email)."""
    res = supabase.table('weekly_reports')\
        .select('student_id')\
        .eq('student_id', student_id)\
        .eq('week_start', str(week_start))\
        .limit(1).execute()
    return bool(res.data)


# Weekly sending lives in weekly_report_runner.py (used by GitHub Actions).
