from collections import defaultdict
from datetime import date, datetime, timedelta

from src.database.config import supabase
from src.database.fast_queries import (
    paginate, get_students_with_parents,
    get_enrollments_for_students, get_logs_between,
)
from src.services.email_service import close_smtp
from src.services.email_rules import emails_conflict
from src.services.weekly_report_service import send_weekly_parent_email


def last_full_week(today=None):
    today = today or date.today()
    start = today - timedelta(days=today.weekday() + 7)  # last Monday
    return start, start + timedelta(days=6)              # last Sunday


def _flush(rows):
    if rows:
        try:
            supabase.table("weekly_reports").insert(rows).execute()
        except Exception as e:
            print(f"  weekly_reports save failed: {e}")
    return []


def send_weekly_reports_to_all_parents(force=False):
    """force=True re-sends even to parents already emailed for the week."""
    ws, we = last_full_week()
    start_dt = datetime.combine(ws, datetime.min.time())
    end_dt = datetime.combine(we + timedelta(days=1), datetime.min.time())
    print(f"Weekly reports for {ws} to {we}")

    students = get_students_with_parents()
    if not students:
        return 0, 0

    enroll = get_enrollments_for_students([s["student_id"] for s in students])

    counts = defaultdict(lambda: [0, 0])  # (student, subject) -> [total, present]
    for l in get_logs_between(start_dt, end_dt):
        c = counts[(l["student_id"], l["subject_id"])]
        c[0] += 1
        if l.get("is_present"):
            c[1] += 1

    done = {
        (r["student_id"], r["subject_id"])
        for r in paginate(lambda: (
            supabase.table("weekly_reports")
            .select("student_id,subject_id")
            .eq("week_start", str(ws)).eq("email_sent", True)
            .order("student_id").order("subject_id")
        ))
    }

    if force:
        done = set()

    success = failed = 0
    pending = []
    try:
        for s in students:
            sid = s["student_id"]
            subs = enroll.get(sid, [])
            if not subs:
                continue
            if all((sid, sub["subject_id"]) in done for sub in subs):
                continue  # already emailed this week

            reports = []
            for sub in subs:
                total, att = counts.get((sid, sub["subject_id"]), (0, 0))
                reports.append({
                    "subject_id": sub["subject_id"],
                    "subject_name": sub["name"],
                    "subject_code": sub["subject_code"],
                    "total": total,
                    "attended": att,
                    "absent": total - att,
                    "attendance_pct": round(att / total * 100, 1) if total else 0,
                })
            if not any(r["total"] for r in reports):
                continue  # no classes this week, skip the noise

            if emails_conflict(s.get("email"), s.get("parent_email")):
                print(f"  skipped {s.get('name')}: parent email is the same as the student email")
                continue

            try:
                send_weekly_parent_email(
                    parent_name=s.get("parent_name") or "Parent",
                    parent_email=s["parent_email"],
                    student_name=s["name"],
                    roll_no=s.get("roll_no") or "N/A",
                    section=s.get("section") or "N/A",
                    subject_reports=reports,
                    week_start=ws, week_end=we,
                )
            except Exception as e:
                failed += 1
                print(f"  failed for {s.get('name')}: {e}")
                continue

            success += 1
            pending += [{
                "student_id": sid, "subject_id": r["subject_id"],
                "week_start": str(ws), "week_end": str(we),
                "total_classes": r["total"], "attended": r["attended"],
                "absent": r["absent"], "attendance_pct": r["attendance_pct"],
                "email_sent": True,
            } for r in reports]
            if len(pending) >= 100:
                pending = _flush(pending)
    finally:
        _flush(pending)
        close_smtp()

    print(f"Done. Success: {success}, Failed: {failed}")
    return success, failed
