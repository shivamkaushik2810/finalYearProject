import os
from datetime import date, timedelta
from src.database.db import (
    get_all_enrolled_students_with_parents,
    get_enrolled_subjects_map,
    get_weekly_attendance_bulk,
    get_reported_student_ids,
    save_weekly_reports_bulk,
)
from src.services.weekly_report_service import send_weekly_parent_email
from src.services.mail_pool import pooled_smtp

MAX_EMAILS_PER_RUN = int(os.getenv("MAX_EMAILS_PER_RUN", "450"))   # Gmail daily limit safety
DRY_RUN = os.getenv("DRY_RUN") == "1"
TEST_EMAIL_TO = os.getenv("TEST_EMAIL_TO")                          # test mode: all mail goes here
TEST_LIMIT = int(os.getenv("TEST_LIMIT", "3"))


def last_full_week(today=None):
    """Previous Monday-Sunday, whichever day of the week this runs."""
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def report_week(mode="last", today=None):
    today = today or date.today()
    if mode == "current":
        return today - timedelta(days=today.weekday()), today
    return last_full_week(today)


def send_weekly_reports_to_all_parents(force=False):
    mode = os.getenv("REPORT_WEEK", "last").lower()
    if mode == "current" and not TEST_EMAIL_TO:
        raise ValueError(
            "REPORT_WEEK=current needs TEST_EMAIL_TO=<your address>. "
            "Reports for a partial week must never go to real parents.")

    test = bool(TEST_EMAIL_TO)
    week_start, week_end = report_week(mode)
    tag = "  [DRY RUN]" if DRY_RUN else ("  [TEST -> " + TEST_EMAIL_TO + "]" if test else "")
    print(f"Weekly reports for {week_start} to {week_end}{tag}")

    students = get_all_enrolled_students_with_parents()
    total_parents = len(students)
    done = set()
    if not force and not test:
        done = get_reported_student_ids(week_start)
        students = [s for s in students if s['student_id'] not in done]
    print(f"Students with a parent email: {total_parents} | already reported: {len(done)} "
          f"| to check: {len(students)}")
    if not students:
        print("Nothing to send.")
        return 0, 0

    subjects_map = get_enrolled_subjects_map()
    counts = get_weekly_attendance_bulk(week_start, week_end)
    limit = TEST_LIMIT if test else MAX_EMAILS_PER_RUN

    success, failed, no_classes, pending = 0, 0, 0, []
    try:
        with pooled_smtp():
            for stu in students:
                if success >= limit:
                    print(f"Limit of {limit} emails reached. "
                          f"The rest will be sent on the next run.")
                    break
                sid = stu['student_id']
                try:
                    if not stu.get('parent_email'):
                        continue
                    if not TEST_EMAIL_TO and stu['parent_email'].strip().lower().endswith('.invalid'):
                        continue   # QA/test addresses never receive real mail
                    reports, rows = [], []
                    for sub in subjects_map.get(sid, []):
                        total, attended = counts.get((sid, sub['subject_id']), (0, 0))
                        if total == 0:
                            continue
                        absent = total - attended
                        pct = round(attended / total * 100, 1)
                        reports.append({
                            'subject_name': sub['name'], 'subject_code': sub['subject_code'],
                            'total': total, 'attended': attended,
                            'absent': absent, 'attendance_pct': pct
                        })
                        rows.append({
                            'student_id': sid, 'subject_id': sub['subject_id'],
                            'week_start': str(week_start), 'week_end': str(week_end),
                            'total_classes': total, 'attended': attended,
                            'absent': absent, 'attendance_pct': pct, 'email_sent': True
                        })
                    if not reports:
                        no_classes += 1
                        continue

                    to_addr = TEST_EMAIL_TO or stu['parent_email']
                    if DRY_RUN:
                        print(f"  [dry] would email {to_addr} for {stu['name']}")
                        success += 1
                        continue

                    send_weekly_parent_email(
                        parent_name=stu.get('parent_name') or 'Parent',
                        parent_email=to_addr,
                        student_name=stu['name'],
                        roll_no=stu.get('roll_no') or 'N/A',
                        section=stu.get('section') or 'N/A',
                        subject_reports=reports,
                        week_start=week_start, week_end=week_end
                    )
                    if not test:
                        pending.extend(rows)   # saved only after the email really went out
                    success += 1
                    if len(pending) >= 500:
                        save_weekly_reports_bulk(pending)
                        pending = []
                except Exception as e:
                    failed += 1
                    print(f"  ❌ Failed for {stu.get('name', 'Unknown')}: {e}")
    finally:
        if pending:
            save_weekly_reports_bulk(pending)

    print(f"Skipped (no classes in {week_start} to {week_end}): {no_classes}")
    print(f"Done! Success: {success}, Failed: {failed}")
    return success, failed
