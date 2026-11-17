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
    tone = "good" if overall >= 75 else "bad" if overall < 50 else "avg"
    overall_label = "Good" if overall >= 75 else "Needs Improvement" if overall < 50 else "Average"

    def status(p):
        return ("Good", "#27500A") if p >= 75 else ("At Risk", "#791F1F") if p < 50 else ("Average", "#633806")

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
        + (T.notice("Action Required: Attendance is below 75%. Please ensure regular attendance "
                    "to avoid academic consequences.") if overall < 75 else "")
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


def send_weekly_reports_to_all_parents():
    """
    Send weekly reports to all parents (previous Monday-Sunday).
    Idempotent per student+week. Returns (success, failed).
    """
    today      = date.today()
    week_end   = today - timedelta(days=1)
    week_start = week_end - timedelta(days=6)
    ts_start = f"{week_start}T00:00:00"
    ts_end   = f"{week_end}T23:59:59"

    print(f"Sending weekly reports for {week_start} to {week_end}")

    students = get_all_enrolled_students_with_parents()
    success = failed = skipped = 0

    for student in students:
        try:
            student_id   = student['student_id']
            parent_email = student.get('parent_email')
            parent_name  = student.get('parent_name') or 'Parent'

            if not parent_email:
                continue
            if _already_reported(student_id, week_start):
                skipped += 1
                continue

            subject_nodes = get_subjects_for_student(student_id)
            if not subject_nodes:
                continue

            subject_reports = []
            for node in subject_nodes:
                sub = node.get('subjects')
                if not sub:
                    continue
                logs = get_weekly_attendance(
                    student_id, sub['subject_id'], ts_start, ts_end)
                total = len(logs)
                if total == 0:
                    continue
                attended = sum(1 for l in logs if l.get('is_present'))
                subject_reports.append({
                    'subject_id':     sub['subject_id'],
                    'subject_name':   sub['name'],
                    'subject_code':   sub['subject_code'],
                    'total':          total,
                    'attended':       attended,
                    'absent':         total - attended,
                    'attendance_pct': round((attended / total) * 100, 1)
                })

            if not subject_reports:
                continue

            send_weekly_parent_email(
                parent_name=parent_name, parent_email=parent_email,
                student_name=student['name'],
                roll_no=student.get('roll_no') or 'N/A',
                section=student.get('section') or 'N/A',
                subject_reports=subject_reports,
                week_start=week_start, week_end=week_end)

            for r in subject_reports:
                save_weekly_report(
                    student_id, r['subject_id'], week_start, week_end,
                    r['total'], r['attended'], r['absent'], r['attendance_pct'])
            success += 1
            print(f"  Sent weekly report for student_id={student_id}")

        except Exception as e:
            failed += 1
            print(f"  Failed for student_id={student.get('student_id')}: {type(e).__name__}")

    print(f"\nDone! Success: {success}, Failed: {failed}, Skipped: {skipped}")
    return success, failed
