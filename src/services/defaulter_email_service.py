import html
import io
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.services.email_service import _get_config


class _Raw(str):
    """Trusted HTML fragment that must not be escaped."""


def _e(v):
    return v if isinstance(v, _Raw) else html.escape("" if v is None else str(v))


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _attendance_chart(subject_rows):
    names = [r["subject"] for r in subject_rows]
    pcts = [r["pct"] for r in subject_rows]
    colors = ["#28a745" if p >= 75 else "#f39c12" if p >= 50 else "#e74c3c" for p in pcts]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.bar(names, pcts, color=colors)
    ax.axhline(75, color="#5865F2", ls="--", lw=1)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Attendance %")
    ax.set_title("Subject-wise Attendance (dashed line = 75%)")
    plt.xticks(rotation=25, ha="right")
    return _png(fig)


def _trend_chart(monthly):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.plot(monthly["month"], monthly["pct"], marker="o", color="#5865F2")
    ax.axhline(75, color="#e74c3c", ls="--", lw=1)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Attendance %")
    ax.set_title("Monthly Attendance Trend")
    plt.xticks(rotation=25, ha="right")
    return _png(fig)


def _marks_chart(marks_rows):
    names = [f"{r['subject']} ({r['exam']})" for r in marks_rows]
    pcts = [r["pct"] for r in marks_rows]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.barh(names, pcts, color="#EB459E")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Marks %")
    ax.set_title("Marks by Subject / Exam")
    return _png(fig)


def _table(headers, rows):
    th = "".join(f"<th style='padding:8px 10px;background:#f8f9fa;font-size:13px;"
                 f"text-align:left;border-bottom:1px solid #ddd;'>{_e(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(
            f"<td style='padding:8px 10px;border-bottom:1px solid #eee;font-size:13px;'>{_e(c)}</td>"
            for c in r) + "</tr>"
    if not rows:
        body = f"<tr><td colspan='{len(headers)}' style='padding:10px;color:#999;'>No records</td></tr>"
    return (f"<table width='100%' cellpadding='0' cellspacing='0' "
            f"style='border:1px solid #eee;border-collapse:collapse;'>"
            f"<tr>{th}</tr>{body}</table>")


def send_defaulter_report(parent_email, parent_name, student, overall_pct,
                          subject_rows, session_rows, marks_rows, monthly):
    """
    student: dict(name, roll_no, section, course, year)
    subject_rows: [{subject, attended, total, pct}]
    session_rows: [(date_str, subject, 'Present'/'Absent')]
    marks_rows:   [{subject, exam, obtained, max, pct}]
    monthly:      DataFrame(month, pct)
    """
    cfg = _get_config()
    msg = MIMEMultipart("related")
    msg["Subject"] = f"⚠️ Attendance Alert — {student['name']} ({overall_pct}%)"
    msg["From"] = f"SnapClass <{cfg['sender_email']}>"
    msg["To"] = parent_email

    images = {}
    if subject_rows:
        images["att"] = _attendance_chart(subject_rows)
    if monthly is not None and len(monthly) > 1:
        images["trend"] = _trend_chart(monthly)
    if marks_rows:
        images["marks"] = _marks_chart(marks_rows)

    subj_tbl = _table(
        ["Subject", "Attended", "Total", "Percentage"],
        [(r["subject"], r["attended"], r["total"], f"{r['pct']}%") for r in subject_rows])
    marks_tbl = _table(
        ["Subject", "Exam", "Marks", "Percentage"],
        [(r["subject"], r["exam"], f"{r['obtained']}/{r['max']}", f"{r['pct']}%")
         for r in marks_rows])
    sess_tbl = _table(
        ["Date", "Subject", "Status"],
        [(d, s, _Raw(f"<b style='color:{'#28a745' if st == 'Present' else '#e74c3c'}'>{_e(st)}</b>"))
         for d, s, st in session_rows])

    def img(key, alt):
        return (f"<img src='cid:{key}' alt='{alt}' style='max-width:100%;margin:10px 0;'/>"
                if key in images else "")

    html = f"""<html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">
<div style="max-width:680px;margin:auto;background:#fff;border-radius:12px;padding:24px;">
<h2 style="color:#5865F2;margin-top:0;">📷 SnapClass — Attendance Alert</h2>
<p>Dear <b>{_e(parent_name or 'Parent')}</b>,</p>
<p>The overall attendance of your ward <b>{_e(student['name'])}</b>
(Roll {_e(student.get('roll_no') or 'N/A')}, {_e(student.get('course') or '')}
Year {_e(student.get('year') or '')}, Section {_e(student.get('section') or 'N/A')})
is <b style="color:#e74c3c;">{overall_pct}%</b>, which is below the required 75%.</p>
<h3>Subject-wise Attendance</h3>{subj_tbl}{img('att', 'attendance')}
<h3>Monthly Trend</h3>{img('trend', 'trend') or '<p style="color:#999">Not enough data.</p>'}
<h3>Marks</h3>{marks_tbl}{img('marks', 'marks')}
<h3>Recent Attendance Records</h3>{sess_tbl}
<p style="color:#999;font-size:12px;margin-top:20px;">
Automated message from SnapClass. Please encourage regular attendance.</p>
</div></body></html>"""

    plain = (f"Dear {parent_name or 'Parent'},\n\nAttendance of {student['name']} is "
             f"{overall_pct}% (below 75%).\n\n" +
             "\n".join(f"{r['subject']}: {r['attended']}/{r['total']} ({r['pct']}%)"
                       for r in subject_rows) + "\n\n— SnapClass")

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)
    for cid, data in images.items():
        part = MIMEImage(data, _subtype="png")
        part.add_header("Content-ID", f"<{cid}>")
        part.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls()
        s.login(cfg["sender_email"], cfg["sender_password"])
        s.sendmail(cfg["sender_email"], parent_email, msg.as_string())
