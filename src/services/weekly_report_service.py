from datetime import datetime, timedelta, date
import html as _html
from src.database.config import supabase
from src.database.db import (
    get_all_enrolled_students_with_parents,
    get_subjects_for_student,
    get_weekly_attendance,
    save_weekly_report
)
from src.services.email_service import _send


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
    week_end_str   = _fmt_date(week_end)

    # Build subject rows for HTML
    rows_html = ""
    rows_plain = ""
    overall_total   = 0
    overall_present = 0

    for r in subject_reports:
        pct   = r['attendance_pct']
        color = "#28a745" if pct >= 75 else "#e74c3c" if pct < 50 else "#f39c12"
        status = "Good ✅" if pct >= 75 else "At Risk 🔴" if pct < 50 else "Average ⚠️"

        rows_html += f"""
        <tr>
          <td style='padding:10px 12px;border-bottom:1px solid #eee;
                     font-size:13px;color:#333;'>{_html.escape(str(r['subject_name']))}</td>
          <td style='padding:10px 12px;border-bottom:1px solid #eee;
                     font-size:13px;text-align:center;'>{r['attended']}/{r['total']}</td>
          <td style='padding:10px 12px;border-bottom:1px solid #eee;
                     font-size:13px;text-align:center;font-weight:bold;
                     color:{color};'>{pct}%</td>
          <td style='padding:10px 12px;border-bottom:1px solid #eee;
                     font-size:13px;text-align:center;'>{status}</td>
        </tr>"""

        rows_plain += f"  {r['subject_name']}: {r['attended']}/{r['total']} ({pct}%) — {status}\n"
        overall_total   += r['total']
        overall_present += r['attended']

    overall_pct = round((overall_present / overall_total) * 100, 1) if overall_total > 0 else 0
    overall_color = "#28a745" if overall_pct >= 75 else "#e74c3c" if overall_pct < 50 else "#f39c12"
    overall_status = "Good" if overall_pct >= 75 else "Needs Improvement" if overall_pct < 50 else "Average"

    plain = f"""Dear {parent_name},

Weekly Attendance Report for {student_name}
Week: {week_start_str} to {week_end_str}
Roll No: {roll_no} | Section: {section}

Subject-wise Attendance:
{rows_plain}

Overall Attendance: {overall_present}/{overall_total} ({overall_pct}%) — {overall_status}

This is an automated weekly report from SnapClass.
"""

    parent_name  = _html.escape(str(parent_name))
    student_name = _html.escape(str(student_name))
    roll_no      = _html.escape(str(roll_no or 'N/A'))
    section      = _html.escape(str(section or 'N/A'))

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
 <tr><td align="center">
  <table width="620" cellpadding="0" cellspacing="0"
   style="background:#fff;border-radius:12px;overflow:hidden;
          box-shadow:0 4px 14px rgba(0,0,0,.1);">

   <tr><td style="background:linear-gradient(135deg,#1A5276,#2E86C1);
                  padding:28px;text-align:center;">
     <h1 style="color:#fff;margin:0;font-size:24px;">📷 SnapClass</h1>
     <p style="color:#d6eaf8;margin:5px 0 0;font-size:13px;">
       Weekly Attendance Report</p>
   </td></tr>

   <tr><td style="padding:24px 36px 8px;">
     <p style="color:#333;font-size:15px;margin:0;">
       Dear <strong>{parent_name}</strong>,</p>
     <p style="color:#555;font-size:14px;margin:8px 0;">
       Here is the weekly attendance report for your ward:</p>
   </td></tr>

   <tr><td style="padding:8px 36px;">
     <table width="100%" cellpadding="10" cellspacing="0"
      style="background:#eaf4fb;border-radius:10px;
             border-left:5px solid #2E86C1;">
       <tr>
         <td style="color:#888;font-size:13px;width:130px;">👤 Student</td>
         <td style="color:#222;font-size:14px;font-weight:bold;">{student_name}</td>
       </tr>
       <tr>
         <td style="color:#888;font-size:13px;">🎫 Roll No.</td>
         <td style="color:#222;font-size:14px;">{roll_no or 'N/A'}</td>
       </tr>
       <tr>
         <td style="color:#888;font-size:13px;">📚 Section</td>
         <td style="color:#222;font-size:14px;">{section or 'N/A'}</td>
       </tr>
       <tr>
         <td style="color:#888;font-size:13px;">📅 Week</td>
         <td style="color:#222;font-size:14px;">
           {week_start_str} — {week_end_str}</td>
       </tr>
     </table>
   </td></tr>

   <tr><td style="padding:16px 36px 8px;">
     <p style="color:#333;font-size:14px;font-weight:bold;margin:0 0 8px;">
       📊 Subject-wise Attendance:</p>
     <table width="100%" cellpadding="0" cellspacing="0"
      style="border:1px solid #eee;border-radius:8px;overflow:hidden;">
       <tr style="background:#f8f9fa;">
         <th style="padding:10px 12px;text-align:left;
                    font-size:13px;color:#555;">Subject</th>
         <th style="padding:10px 12px;text-align:center;
                    font-size:13px;color:#555;">Classes</th>
         <th style="padding:10px 12px;text-align:center;
                    font-size:13px;color:#555;">Percentage</th>
         <th style="padding:10px 12px;text-align:center;
                    font-size:13px;color:#555;">Status</th>
       </tr>
       {rows_html or "<tr><td colspan='4' style='padding:12px;color:#999;text-align:center;'>No classes this week</td></tr>"}
     </table>
   </td></tr>

   <tr><td style="padding:16px 36px 8px;">
     <table width="100%" cellpadding="0" cellspacing="0">
       <tr>
         <td width="32%" align="center"
             style="background:#d4edda;border-radius:10px;padding:14px;">
           <div style="font-size:26px;font-weight:bold;
                       color:#155724;">{overall_present}</div>
           <div style="font-size:12px;color:#155724;">Present</div>
         </td>
         <td width="4%"></td>
         <td width="32%" align="center"
             style="background:#f8d7da;border-radius:10px;padding:14px;">
           <div style="font-size:26px;font-weight:bold;
                       color:#721c24;">{overall_total - overall_present}</div>
           <div style="font-size:12px;color:#721c24;">Absent</div>
         </td>
         <td width="4%"></td>
         <td width="32%" align="center"
             style="background:#d1ecf1;border-radius:10px;padding:14px;">
           <div style="font-size:26px;font-weight:bold;
                       color:{overall_color};">{overall_pct}%</div>
           <div style="font-size:12px;color:{overall_color};">{overall_status}</div>
         </td>
       </tr>
     </table>
   </td></tr>

   {"<tr><td style='padding:12px 36px;'><div style='background:#fdf3cd;border-radius:8px;padding:12px;border-left:4px solid #f39c12;'><p style='color:#856404;font-size:13px;margin:0;'>⚠️ <strong>Action Required:</strong> Attendance is below 75%. Please ensure regular attendance to avoid academic consequences.</p></div></td></tr>" if overall_pct < 75 else ""}

   <tr><td style="padding:10px 36px 20px;">
     <p style="color:#999;font-size:12px;margin:0;">
       This is an automated weekly report from SnapClass.
       Reports are sent every Monday for the previous week.</p>
   </td></tr>

   <tr><td style="background:#eaf4fb;padding:14px 36px;text-align:center;
                  border-top:1px solid #d6eaf8;">
     <p style="color:#2E86C1;font-size:12px;margin:0;font-weight:bold;">
       SnapClass — Making Attendance Smarter with AI</p>
   </td></tr>

  </table>
 </td></tr>
</table>
</body></html>"""

    _send(
        parent_email,
        f"📊 Weekly Attendance Report — {_html.unescape(student_name)} | {week_start_str} to {week_end_str}",
        html, plain
    )


def send_weekly_reports_to_all_parents():
    """
    Send the report for the last full Mon-Sun week to every parent.
    Safe to run repeatedly: students already reported for that week are skipped.
    Returns (success, failed).
    """
    from src.database.db import weekly_report_exists

    today      = date.today()
    week_start = today - timedelta(days=today.weekday() + 7)   # last Monday
    week_end   = week_start + timedelta(days=6)                # last Sunday
    start_iso  = f"{week_start}T00:00:00"
    end_excl   = f"{week_end + timedelta(days=1)}T00:00:00"    # whole Sunday included

    print(f"Sending weekly reports for {week_start} to {week_end}")

    students = get_all_enrolled_students_with_parents()
    success, failed, skipped = 0, 0, 0

    for student in students:
        try:
            student_id   = student['student_id']
            parent_email = (student.get('parent_email') or '').strip()
            parent_name  = student.get('parent_name') or 'Parent'

            if not parent_email or parent_email.lower().endswith('@example.com'):
                continue

            if weekly_report_exists(student_id, week_start):
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

                logs = get_weekly_attendance(student_id, sub['subject_id'], start_iso, end_excl)
                logs = [l for l in logs if l.get('status') not in ('excused', 'cancelled')]
                total = len(logs)
                if total == 0:
                    continue   # no classes held -> don't show a misleading 0%

                attended = sum(1 for l in logs if l.get('is_present'))
                absent   = total - attended
                pct      = round((attended / total) * 100, 1)

                subject_reports.append({
                    'subject_id':     sub['subject_id'],
                    'subject_name':   sub['name'],
                    'subject_code':   sub['subject_code'],
                    'total':          total,
                    'attended':       attended,
                    'absent':         absent,
                    'attendance_pct': pct
                })

            if not subject_reports:
                continue

            # 1) send the email first ...
            send_weekly_parent_email(
                parent_name     = parent_name,
                parent_email    = parent_email,
                student_name    = student['name'],
                roll_no         = student.get('roll_no') or 'N/A',
                section         = student.get('section') or 'N/A',
                subject_reports = subject_reports,
                week_start      = week_start,
                week_end        = week_end
            )
            # 2) ... and only then record it as sent
            for r in subject_reports:
                save_weekly_report(
                    student_id, r['subject_id'], week_start, week_end,
                    r['total'], r['attended'], r['absent'], r['attendance_pct']
                )
            success += 1
            print(f"  ✅ Sent to parent of {student['name']}")

        except Exception as e:
            failed += 1
            print(f"  ❌ Failed for {student.get('name', 'Unknown')}: {e}")

    print(f"\nDone! Success: {success}, Failed: {failed}, Already sent: {skipped}")
    return success, failed
