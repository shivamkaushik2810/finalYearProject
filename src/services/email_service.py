import smtplib
import threading
import html as _html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import streamlit as st


def _get_config():
    return {
        "sender_email": st.secrets["EMAIL_ADDRESS"],
        "sender_password": st.secrets["EMAIL_PASSWORD"],
    }


_conn = None
_lock = threading.Lock()


def _connect(config):
    srv = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
    srv.ehlo()
    srv.starttls()
    srv.ehlo()
    srv.login(config["sender_email"], config["sender_password"])
    return srv


def close_smtp():
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.quit()
            except Exception:
                pass
            _conn = None


def _send(to_email, subject, html, plain):
    global _conn
    config = _get_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"SnapClass <{config['sender_email']}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    data = msg.as_string()
    with _lock:
        for attempt in (1, 2):
            try:
                if _conn is None:
                    _conn = _connect(config)
                _conn.sendmail(config["sender_email"], to_email, data)
                return
            except (smtplib.SMTPServerDisconnected, OSError):
                try:
                    if _conn is not None:
                        _conn.close()
                except Exception:
                    pass
                _conn = None
                if attempt == 2:
                    raise


def _fmt(ts):
    try:
        return datetime.fromisoformat(ts).strftime("%d %B %Y, %I:%M %p")
    except Exception:
        return ts


def send_student_attendance_email(student_name, student_email,
                                   subject_name, subject_code,
                                   teacher_name, timestamp):
    ft = _fmt(timestamp)
    plain = f"""Dear {student_name},

Your attendance has been successfully marked!

Subject  : {subject_name} ({subject_code})
Teacher  : {teacher_name}
Date     : {ft}
Status   : Present

This is an automated message from SnapClass.
"""
    student_name, subject_name, subject_code, teacher_name, ft = (
        _html.escape(str(v)) for v in (student_name, subject_name, subject_code, teacher_name, ft))
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
 <tr><td align="center">
  <table width="580" cellpadding="0" cellspacing="0"
   style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.1);">
   <tr><td style="background:linear-gradient(135deg,#6C3FC5,#E8386D);padding:28px;text-align:center;">
     <h1 style="color:#fff;margin:0;font-size:26px;">📷 SnapClass</h1>
     <p style="color:#e0d7ff;margin:5px 0 0;font-size:13px;">AI-Powered Attendance System</p>
   </td></tr>
   <tr><td style="padding:28px 36px 10px;text-align:center;">
     <div style="display:inline-block;background:#d4edda;border-radius:50px;padding:10px 26px;">
       <span style="color:#155724;font-size:17px;font-weight:bold;">✅ Attendance Marked Successfully</span>
     </div>
   </td></tr>
   <tr><td style="padding:16px 36px 8px;">
     <p style="color:#333;font-size:15px;margin:0;">Dear <strong>{student_name}</strong>,</p>
     <p style="color:#555;font-size:14px;margin:8px 0 0;">Your attendance has been recorded for the following class:</p>
   </td></tr>
   <tr><td style="padding:14px 36px;">
     <table width="100%" cellpadding="10" cellspacing="0"
      style="background:#f8f5ff;border-radius:10px;border-left:5px solid #6C3FC5;">
       <tr><td style="color:#888;font-size:13px;width:130px;">📚 Subject</td>
           <td style="color:#222;font-size:14px;font-weight:bold;">{subject_name}</td></tr>
       <tr><td style="color:#888;font-size:13px;">🔖 Code</td>
           <td style="color:#222;font-size:14px;">{subject_code}</td></tr>
       <tr><td style="color:#888;font-size:13px;">👨‍🏫 Teacher</td>
           <td style="color:#222;font-size:14px;">{teacher_name}</td></tr>
       <tr><td style="color:#888;font-size:13px;">📅 Date &amp; Time</td>
           <td style="color:#222;font-size:14px;">{ft}</td></tr>
       <tr><td style="color:#888;font-size:13px;">🎯 Status</td>
           <td style="color:#28a745;font-size:14px;font-weight:bold;">Present</td></tr>
     </table>
   </td></tr>
   <tr><td style="padding:10px 36px 20px;">
     <p style="color:#999;font-size:12px;margin:0;">This is an automated notification. Do not reply to this email.</p>
   </td></tr>
   <tr><td style="background:#f0eeff;padding:16px 36px;text-align:center;border-top:1px solid #e0d7ff;">
     <p style="color:#9370DB;font-size:13px;margin:0;font-weight:bold;">SnapClass — Making Attendance Smarter with AI</p>
     <p style="color:#bbb;font-size:11px;margin:4px 0 0;">© 2026 SnapClass. All rights reserved.</p>
   </td></tr>
  </table>
 </td></tr>
</table>
</body></html>"""
    _send(student_email, f"✅ Attendance Marked — {_html.unescape(subject_name)} ({_html.unescape(subject_code)})", html, plain)


def send_teacher_summary_email(teacher_name, teacher_email,
                                subject_name, subject_code,
                                timestamp, present_students, total_enrolled):
    ft = _fmt(timestamp)
    present_count = len(present_students)
    absent_count  = total_enrolled - present_count

    rows_html = "".join(
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #eee;font-size:13px;color:#333;'>"
        f"{i+1}. {_html.escape(str(s['name']))}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#28a745;font-size:13px;font-weight:bold;'>"
        f"✅ Present</td></tr>"
        for i, s in enumerate(present_students)
    )
    rows_plain = "\n".join(f"  {i+1}. {s['name']} — Present" for i, s in enumerate(present_students))

    plain = f"""Dear {teacher_name},

Attendance Summary for your class:

Subject  : {subject_name} ({subject_code})
Date     : {ft}
Present  : {present_count} / {total_enrolled}
Absent   : {absent_count}

Present Students:
{rows_plain}

This is an automated message from SnapClass.
"""
    teacher_name, subject_name, subject_code, ft = (
        _html.escape(str(v)) for v in (teacher_name, subject_name, subject_code, ft))
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
 <tr><td align="center">
  <table width="600" cellpadding="0" cellspacing="0"
   style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.1);">
   <tr><td style="background:linear-gradient(135deg,#1A5276,#2E86C1);padding:28px;text-align:center;">
     <h1 style="color:#fff;margin:0;font-size:26px;">📷 SnapClass</h1>
     <p style="color:#d6eaf8;margin:5px 0 0;font-size:13px;">Attendance Summary Report</p>
   </td></tr>
   <tr><td style="padding:24px 36px 8px;">
     <p style="color:#333;font-size:15px;margin:0;">Dear <strong>{teacher_name}</strong>,</p>
     <p style="color:#555;font-size:14px;margin:8px 0 0;">Attendance has been recorded. Here is your summary:</p>
   </td></tr>
   <tr><td style="padding:10px 36px;">
     <table width="100%" cellpadding="10" cellspacing="0"
      style="background:#eaf4fb;border-radius:10px;border-left:5px solid #2E86C1;">
       <tr><td style="color:#888;font-size:13px;width:130px;">📚 Subject</td>
           <td style="color:#222;font-size:14px;font-weight:bold;">{subject_name}</td></tr>
       <tr><td style="color:#888;font-size:13px;">🔖 Code</td>
           <td style="color:#222;font-size:14px;">{subject_code}</td></tr>
       <tr><td style="color:#888;font-size:13px;">📅 Date &amp; Time</td>
           <td style="color:#222;font-size:14px;">{ft}</td></tr>
     </table>
   </td></tr>
   <tr><td style="padding:16px 36px 8px;">
     <table width="100%" cellpadding="0" cellspacing="8">
       <tr>
         <td width="32%" align="center" style="background:#d4edda;border-radius:10px;padding:16px;">
           <div style="font-size:28px;font-weight:bold;color:#155724;">{present_count}</div>
           <div style="font-size:12px;color:#155724;">Present</div></td>
         <td width="4%"></td>
         <td width="32%" align="center" style="background:#f8d7da;border-radius:10px;padding:16px;">
           <div style="font-size:28px;font-weight:bold;color:#721c24;">{absent_count}</div>
           <div style="font-size:12px;color:#721c24;">Absent</div></td>
         <td width="4%"></td>
         <td width="32%" align="center" style="background:#d1ecf1;border-radius:10px;padding:16px;">
           <div style="font-size:28px;font-weight:bold;color:#0c5460;">{total_enrolled}</div>
           <div style="font-size:12px;color:#0c5460;">Total</div></td>
       </tr>
     </table>
   </td></tr>
   <tr><td style="padding:16px 36px 8px;">
     <p style="color:#333;font-size:14px;font-weight:bold;margin:0 0 8px;">📋 Present Students:</p>
     <table width="100%" cellpadding="0" cellspacing="0"
      style="border:1px solid #eee;border-radius:8px;overflow:hidden;">
       <tr style="background:#f8f9fa;">
         <th style="padding:10px 12px;text-align:left;font-size:13px;color:#555;">Student Name</th>
         <th style="padding:10px 12px;text-align:left;font-size:13px;color:#555;">Status</th>
       </tr>
       {rows_html or "<tr><td colspan='2' style='padding:12px;color:#999;font-size:13px;text-align:center;'>No students were present</td></tr>"}
     </table>
   </td></tr>
   <tr><td style="padding:10px 36px 20px;">
     <p style="color:#999;font-size:12px;margin:0;">This is an automated summary from SnapClass. Do not reply.</p>
   </td></tr>
   <tr><td style="background:#eaf4fb;padding:16px 36px;text-align:center;border-top:1px solid #d6eaf8;">
     <p style="color:#2E86C1;font-size:13px;margin:0;font-weight:bold;">SnapClass — Making Attendance Smarter with AI</p>
     <p style="color:#bbb;font-size:11px;margin:4px 0 0;">© 2026 SnapClass. All rights reserved.</p>
   </td></tr>
  </table>
 </td></tr>
</table>
</body></html>"""
    _send(teacher_email, f"📊 Attendance Summary — {_html.unescape(subject_name)} | {_html.unescape(ft)}", html, plain)


def send_all_attendance_emails(logs, subject_name, subject_code,
                                teacher_name, teacher_email,
                                timestamp, all_enrolled_students):
    student_map  = {s['student_id']: s for s in all_enrolled_students}
    present_list = []
    student_ok   = 0
    student_fail = 0

    for log in logs:
        if not log.get('is_present'):
            continue
        student = student_map.get(log['student_id'])
        if not student:
            continue
        present_list.append(student)
        email = student.get('email')
        if not email:
            student_fail += 1
            continue
        if email.lower().endswith('@example.com'):
            continue
        try:
            send_student_attendance_email(
                student['name'], email,
                subject_name, subject_code,
                teacher_name, timestamp
            )
            student_ok += 1
        except Exception:
            student_fail += 1

    teacher_ok = False
    if teacher_email:
        try:
            send_teacher_summary_email(
                teacher_name, teacher_email,
                subject_name, subject_code,
                timestamp, present_list, len(all_enrolled_students)
            )
            teacher_ok = True
        except Exception:
            pass

    return student_ok, student_fail, teacher_ok
