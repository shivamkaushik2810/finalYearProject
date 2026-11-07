from datetime import datetime, timedelta, date
from src.database.config import supabase
from src.database.db import (
    get_all_enrolled_students_with_parents,
    get_subjects_for_student,
    get_weekly_attendance,
    save_weekly_report
)
from src.services.email_service import _send
from src.services import email_templates as T


def _fmt_date(d):
    if isinstance(d, str):
        d = datetime.fromisoformat(d).date()
    return d.strftime("%d %B %Y")


def send_weekly_parent_email(
    parent_name, parent_email,
    student_name, roll_no, section,
    subject_reports, week_start, week_end
):
    """Send weekly attendance report to parent"""
    week_start_str = _fmt_date(week_start)
    week_end_str = _fmt_date(week_end)
    html, plain = T.weekly_parent_email(parent_name, student_name, roll_no, section,
                                        week_start_str, week_end_str, subject_reports)
    _send(
        parent_email,
        f"Weekly Attendance Report - {student_name} | {week_start_str} to {week_end_str}",
        html, plain
    )


def send_weekly_reports_to_all_parents():
    """
    Main function to send weekly reports to all parents.
    Call this every Monday automatically.
    """
    today      = date.today()
    week_end   = today - timedelta(days=1)          # yesterday (Sunday)
    week_start = week_end - timedelta(days=6)       # last Monday

    print(f"Sending weekly reports for {week_start} to {week_end}")

    students = get_all_enrolled_students_with_parents()
    success  = 0
    failed   = 0

    for student in students:
        try:
            student_id   = student['student_id']
            parent_email = student.get('parent_email')
            parent_name  = student.get('parent_name', 'Parent')

            if not parent_email:
                continue

            # Get all subjects for this student
            subject_nodes = get_subjects_for_student(student_id)
            if not subject_nodes:
                continue

            subject_reports = []
            for node in subject_nodes:
                sub = node.get('subjects')
                if not sub:
                    continue

                subject_id = sub['subject_id']
                logs = get_weekly_attendance(
                    student_id, subject_id,
                    str(week_start), str(week_end)
                )

                total   = len(logs)
                attended = sum(1 for l in logs if l.get('is_present'))
                absent  = total - attended
                pct     = round((attended / total) * 100, 1) if total > 0 else 0

                subject_reports.append({
                    'subject_name':   sub['name'],
                    'subject_code':   sub['subject_code'],
                    'total':          total,
                    'attended':       attended,
                    'absent':         absent,
                    'attendance_pct': pct
                })

                # Save report to DB
                save_weekly_report(
                    student_id, subject_id,
                    week_start, week_end,
                    total, attended, absent, pct
                )

            if subject_reports:
                send_weekly_parent_email(
                    parent_name      = parent_name,
                    parent_email     = parent_email,
                    student_name     = student['name'],
                    roll_no          = student.get('roll_no', 'N/A'),
                    section          = student.get('section', 'N/A'),
                    subject_reports  = subject_reports,
                    week_start       = week_start,
                    week_end         = week_end
                )
                success += 1
                print(f"  ✅ Sent to parent of {student['name']}")

        except Exception as e:
            failed += 1
            print(f"  ❌ Failed for {student.get('name', 'Unknown')}: {e}")

    print(f"\nDone! Success: {success}, Failed: {failed}")
    return success, failed
