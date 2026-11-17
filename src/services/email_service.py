import smtplib
import threading
import html as _html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import streamlit as st
from src.services import email_templates as T


def _get_config():
    return {
        "sender_email": st.secrets["EMAIL_ADDRESS"],
        "sender_password": st.secrets["EMAIL_PASSWORD"],
    }


_local = threading.local()


def smtp_open():
    """Open ONE authenticated connection (via smtp_config) reused by _send in this thread."""
    from src.services.smtp_config import open_smtp
    server, cfg = open_smtp()
    _local.conn, _local.cfg = server, cfg
    return server


def smtp_close():
    conn = getattr(_local, "conn", None)
    _local.conn = None
    _local.cfg = None
    if conn is not None:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def _send(to_email, subject, html, plain):
    config = _get_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = " ".join(str(subject).split())  # no line breaks in headers
    from src.services.smtp_config import get_smtp_settings
    msg["From"]    = f"SnapClass <{get_smtp_settings()['sender']}>"
    msg["To"]      = " ".join(str(to_email).split())
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    conn = getattr(_local, "conn", None)
    if conn is not None:  # batch mode: reuse the open connection
        conn.sendmail(_local.cfg["sender"], to_email, msg.as_string())
        return
    from src.services.smtp_config import open_smtp
    server, cfg = open_smtp()
    try:
        server.sendmail(cfg["sender"], to_email, msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _fmt(ts):
    try:
        return datetime.fromisoformat(ts).strftime("%d %B %Y, %I:%M %p")
    except Exception:
        return ts


def send_student_attendance_email(student_name, student_email,
                                   subject_name, subject_code,
                                   teacher_name, timestamp):
    """Student 'you are marked present' email, on the shared SnapClass template."""
    html, plain = T.student_attendance_email(student_name, subject_name, subject_code,
                                             teacher_name, _fmt(timestamp))
    _send(student_email, f"✅ Attendance Marked — {subject_name} ({subject_code})", html, plain)


def send_teacher_summary_email(teacher_name, teacher_email,
                                subject_name, subject_code,
                                timestamp, present_students, total_enrolled):
    """Teacher summary email, on the shared SnapClass template."""
    ft = _fmt(timestamp)
    html, plain = T.teacher_summary_email(teacher_name, subject_name, subject_code, ft,
                                          [s['name'] for s in present_students], total_enrolled)
    _send(teacher_email, f"📊 Attendance Summary — {subject_name} | {ft}", html, plain)


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
