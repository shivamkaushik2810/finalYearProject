import html as _html
from datetime import datetime

from src.services.email_service import _send  # mail_pool swaps this name for a pooled sender


def _esc(value):
    return _html.escape("" if value is None else str(value))


def _fmt_date(d):
    if isinstance(d, str):
        d = datetime.fromisoformat(d).date()
    return d.strftime("%d %B %Y")


def _status(pct):
    if pct >= 75:
        return "#28a745", "Good ✅"
    if pct < 50:
        return "#e74c3c", "At Risk 🔴"
    return "#f39c12", "Average ⚠️"


def send_weekly_parent_email(parent_name, parent_email, student_name, roll_no,
                             section, subject_reports, week_start, week_end):
    """Send weekly attendance report to one parent. Raises on failure."""
    ws, we = _fmt_date(week_start), _fmt_date(week_end)
    parent_name = parent_name or "Parent"
    roll_no = roll_no or "N/A"
    section = section or "N/A"

    rows_html, rows_plain = "", ""
    total_all = present_all = 0
    for r in subject_reports:
        pct = r["attendance_pct"]
        if not r["total"]:
            color, status, pct = "#888888", "No classes", "—"
        else:
            color, status = _status(pct)
        rows_html += (
            "<tr>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;color:#333;'>{_esc(r['subject_name'])}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:center;'>{r['attended']}/{r['total']}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:center;font-weight:bold;color:{color};'>{pct}{'%' if r['total'] else ''}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:center;'>{status}</td>"
            "</tr>"
        )
        rows_plain += f"  {r['subject_name']}: {r['attended']}/{r['total']} ({pct}{'%' if r['total'] else ''}) — {status}\n"
        total_all += r["total"]
        present_all += r["attended"]

    overall_pct = round(present_all / total_all * 100, 1) if total_all else 0
    o_color = "#28a745" if overall_pct >= 75 else "#e74c3c" if overall_pct < 50 else "#f39c12"
    o_status = "Good" if overall_pct >= 75 else "Needs Improvement" if overall_pct < 50 else "Average"
    warn_html = ""
    if total_all > 0 and overall_pct < 75:
        warn_html = (
            "<tr><td style='padding:12px 36px;'><div style='background:#fdf3cd;border-radius:8px;"
            "padding:12px;border-left:4px solid #f39c12;'><p style='color:#856404;font-size:13px;margin:0;'>"
            "⚠️ <strong>Action Required:</strong> Attendance is below 75%. Please ensure regular "
            "attendance to avoid academic consequences.</p></div></td></tr>"
        )

    plain = f"""Dear {parent_name},

Weekly Attendance Report for {student_name}
Week: {ws} to {we}
Roll No: {roll_no} | Section: {section}

Subject-wise Attendance:
{rows_plain}
Overall Attendance: {present_all}/{total_all} ({overall_pct}%) — {o_status}

This is an automated weekly report from SnapClass.
"""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;"><tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.1);">
<tr><td style="background:linear-gradient(135deg,#1A5276,#2E86C1);padding:28px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:24px;">📷 SnapClass</h1>
<p style="color:#d6eaf8;margin:5px 0 0;font-size:13px;">Weekly Attendance Report</p></td></tr>
<tr><td style="padding:24px 36px 8px;">
<p style="color:#333;font-size:15px;margin:0;">Dear <strong>{_esc(parent_name)}</strong>,</p>
<p style="color:#555;font-size:14px;margin:8px 0;">Here is the weekly attendance report for your ward:</p></td></tr>
<tr><td style="padding:8px 36px;">
<table width="100%" cellpadding="10" cellspacing="0" style="background:#eaf4fb;border-radius:10px;border-left:5px solid #2E86C1;">
<tr><td style="color:#888;font-size:13px;width:130px;">👤 Student</td><td style="color:#222;font-size:14px;font-weight:bold;">{_esc(student_name)}</td></tr>
<tr><td style="color:#888;font-size:13px;">🎫 Roll No.</td><td style="color:#222;font-size:14px;">{_esc(roll_no)}</td></tr>
<tr><td style="color:#888;font-size:13px;">📚 Section</td><td style="color:#222;font-size:14px;">{_esc(section)}</td></tr>
<tr><td style="color:#888;font-size:13px;">📅 Week</td><td style="color:#222;font-size:14px;">{ws} — {we}</td></tr>
</table></td></tr>
<tr><td style="padding:16px 36px 8px;">
<p style="color:#333;font-size:14px;font-weight:bold;margin:0 0 8px;">📊 Subject-wise Attendance:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:8px;overflow:hidden;">
<tr style="background:#f8f9fa;">
<th style="padding:10px 12px;text-align:left;font-size:13px;color:#555;">Subject</th>
<th style="padding:10px 12px;text-align:center;font-size:13px;color:#555;">Classes</th>
<th style="padding:10px 12px;text-align:center;font-size:13px;color:#555;">Percentage</th>
<th style="padding:10px 12px;text-align:center;font-size:13px;color:#555;">Status</th></tr>
{rows_html or "<tr><td colspan='4' style='padding:12px;color:#999;text-align:center;'>No classes this week</td></tr>"}
</table></td></tr>
<tr><td style="padding:16px 36px 8px;"><table width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="32%" align="center" style="background:#d4edda;border-radius:10px;padding:14px;"><div style="font-size:26px;font-weight:bold;color:#155724;">{present_all}</div><div style="font-size:12px;color:#155724;">Present</div></td>
<td width="4%"></td>
<td width="32%" align="center" style="background:#f8d7da;border-radius:10px;padding:14px;"><div style="font-size:26px;font-weight:bold;color:#721c24;">{total_all - present_all}</div><div style="font-size:12px;color:#721c24;">Absent</div></td>
<td width="4%"></td>
<td width="32%" align="center" style="background:#d1ecf1;border-radius:10px;padding:14px;"><div style="font-size:26px;font-weight:bold;color:{o_color};">{overall_pct}%</div><div style="font-size:12px;color:{o_color};">{o_status}</div></td>
</tr></table></td></tr>
{warn_html}
<tr><td style="padding:10px 36px 20px;"><p style="color:#999;font-size:12px;margin:0;">This is an automated weekly report from SnapClass. Reports are sent every Monday for the previous week.</p></td></tr>
<tr><td style="background:#eaf4fb;padding:14px 36px;text-align:center;border-top:1px solid #d6eaf8;">
<p style="color:#2E86C1;font-size:12px;margin:0;font-weight:bold;">SnapClass — Making Attendance Smarter with AI</p></td></tr>
</table></td></tr></table></body></html>"""

    _send(parent_email, f"📊 Weekly Attendance Report — {student_name} | {ws} to {we}", html, plain)
