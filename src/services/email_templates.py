"""One brand template for every SnapClass email. All dynamic values are HTML-escaped."""
import html

BRAND = "#5865F2"
SOFT = "#E0E3FF"
TONES = {
    "good": ("#EAF3DE", "#27500A"),
    "bad": ("#FCEBEB", "#791F1F"),
    "avg": ("#FAEEDA", "#633806"),
    "info": ("#E0E3FF", "#3C3489"),
}


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def shell(title, subtitle, body_html, note="This is an automated message from SnapClass."):
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td bgcolor="{BRAND}" style="background:{BRAND};padding:24px;text-align:center;">
<div style="color:#ffffff;font-size:24px;font-weight:bold;">SnapClass</div>
<div style="color:{SOFT};font-size:13px;margin-top:4px;">{esc(subtitle)}</div></td></tr>
<tr><td style="padding:24px 32px 8px;"><div style="color:#1e293b;font-size:18px;font-weight:bold;">{esc(title)}</div></td></tr>
<tr><td style="padding:8px 32px 16px;">{body_html}</td></tr>
<tr><td style="padding:0 32px 20px;"><div style="color:#64748b;font-size:12px;">{esc(note)}</div></td></tr>
<tr><td bgcolor="{SOFT}" style="background:{SOFT};padding:14px 32px;text-align:center;">
<div style="color:#3C3489;font-size:12px;font-weight:bold;">SnapClass - Making attendance smarter with AI</div></td></tr>
</table></td></tr></table></body></html>"""


def paragraph(text):
    return f'<p style="color:#334155;font-size:14px;margin:0 0 12px;">{esc(text)}</p>'


def info_table(rows):
    """rows: list of (label, value) or (label, value, color)."""
    out = []
    for row in rows:
        label, value = row[0], row[1]
        color = row[2] if len(row) > 2 else "#1e293b"
        out.append(f'<tr><td style="color:#64748b;font-size:13px;padding:6px 0;width:130px;">{esc(label)}</td>'
                   f'<td style="color:{color};font-size:14px;padding:6px 0;font-weight:bold;">{esc(value)}</td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="6" cellspacing="0" '
            f'style="background:#F5F6FF;border-left:5px solid {BRAND};margin:0 0 14px;">{"".join(out)}</table>')


def stat_boxes(items):
    """items: list of (value, label, tone)."""
    cells = []
    for value, label, tone in items:
        bg, fg = TONES.get(tone, TONES["info"])
        cells.append(f'<td align="center" width="33%" style="background:{bg};padding:12px;border-radius:8px;">'
                     f'<div style="font-size:24px;font-weight:bold;color:{fg};">{esc(value)}</div>'
                     f'<div style="font-size:12px;color:{fg};">{esc(label)}</div></td>')
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="6" style="margin:0 0 14px;">'
            f'<tr>{"".join(cells)}</tr></table>')


def data_table(headers, rows):
    """rows: list of lists of (text, color_or_None)."""
    head = "".join(f'<th style="padding:8px 10px;text-align:left;font-size:13px;color:#475569;'
                   f'background:#f1f5f9;">{esc(h)}</th>' for h in headers)
    body = ""
    for row in rows:
        tds = "".join(f'<td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:13px;'
                      f'color:{c or "#1e293b"};">{esc(t)}</td>' for t, c in row)
        body += f"<tr>{tds}</tr>"
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid #e2e8f0;margin:0 0 14px;"><tr>{head}</tr>{body}</table>')


def notice(text):
    return (f'<div style="background:#FAEEDA;border-left:4px solid #BA7517;padding:10px 12px;margin:0 0 14px;'
            f'color:#633806;font-size:13px;">{esc(text)}</div>')


def student_attendance_email(student_name, subject_name, subject_code, teacher_name, when):
    body = (paragraph(f"Dear {student_name}, your attendance has been recorded.")
            + info_table([("Subject", subject_name), ("Code", subject_code), ("Teacher", teacher_name),
                          ("Date and time", when), ("Status", "Present", "#27500A")]))
    plain = (f"Dear {student_name},\n\nYour attendance has been marked.\n\n"
             f"Subject : {subject_name} ({subject_code})\nTeacher : {teacher_name}\n"
             f"Date    : {when}\nStatus  : Present\n\nThis is an automated message from SnapClass.\n")
    return shell("Attendance marked", "Attendance confirmation", body), plain


def teacher_summary_email(teacher_name, subject_name, subject_code, when, present_names, total):
    present = len(present_names)
    absent = total - present
    rows = [[(f"{i + 1}. {n}", None), ("Present", "#27500A")] for i, n in enumerate(present_names)]
    table = data_table(["Student", "Status"], rows) if rows else paragraph("No students were present.")
    body = (paragraph(f"Dear {teacher_name}, attendance has been recorded.")
            + info_table([("Subject", subject_name), ("Code", subject_code), ("Date and time", when)])
            + stat_boxes([(present, "Present", "good"), (absent, "Absent", "bad"), (total, "Total", "info")])
            + table)
    plain_rows = "\n".join(f"  {i + 1}. {n} - Present" for i, n in enumerate(present_names))
    plain = (f"Dear {teacher_name},\n\nAttendance summary\n\nSubject : {subject_name} ({subject_code})\n"
             f"Date    : {when}\nPresent : {present} / {total}\nAbsent  : {absent}\n\n"
             f"Present students:\n{plain_rows}\n\nThis is an automated message from SnapClass.\n")
    return shell("Attendance summary", "Summary for your class", body), plain


def weekly_parent_email(parent_name, student_name, roll_no, section, start, end, subject_reports):
    total = sum(r["total"] for r in subject_reports)
    present = sum(r["attended"] for r in subject_reports)
    overall = round(present / total * 100, 1) if total else 0
    tone = "good" if overall >= 75 else "bad" if overall < 50 else "avg"
    label = "Good" if overall >= 75 else "Needs improvement" if overall < 50 else "Average"

    def tag(p):
        return ("Good", "#27500A") if p >= 75 else ("At risk", "#791F1F") if p < 50 else ("Average", "#633806")

    rows = [[(r["subject_name"], None), (f'{r["attended"]}/{r["total"]}', None), (f'{r["attendance_pct"]}%', tag(r["attendance_pct"])[1]),
             (tag(r["attendance_pct"])[0], tag(r["attendance_pct"])[1])] for r in subject_reports]
    table = (data_table(["Subject", "Classes", "Percentage", "Status"], rows) if rows
             else paragraph("No classes this week."))
    body = (paragraph(f"Dear {parent_name}, here is the weekly attendance report for your ward.")
            + info_table([("Student", student_name), ("Roll no.", roll_no or "N/A"),
                          ("Section", section or "N/A"), ("Week", f"{start} to {end}")])
            + table
            + stat_boxes([(present, "Present", "good"), (total - present, "Absent", "bad"), (f"{overall}%", label, tone)])
            + (notice("Attendance is below 75%. Please ensure regular attendance.") if overall < 75 and total else ""))
    plain_rows = "".join(f'  {r["subject_name"]}: {r["attended"]}/{r["total"]} ({r["attendance_pct"]}%)\n'
                         for r in subject_reports)
    plain = (f"Dear {parent_name},\n\nWeekly attendance report for {student_name}\nWeek: {start} to {end}\n"
             f"Roll No: {roll_no} | Section: {section}\n\nSubject-wise attendance:\n{plain_rows}\n"
             f"Overall: {present}/{total} ({overall}%) - {label}\n\nThis is an automated weekly report from SnapClass.\n")
    return shell("Weekly attendance report", "Weekly report", body,
                 "This is an automated weekly report from SnapClass."), plain
