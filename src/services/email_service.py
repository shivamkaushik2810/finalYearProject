import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from src.services import email_templates as T

log = logging.getLogger(__name__)


def _get_config():
    return {
        "sender_email": st.secrets["EMAIL_ADDRESS"],
        "sender_password": st.secrets["EMAIL_PASSWORD"],
    }


def _clean_header(value):
    """Stop header injection: a subject or name must never contain a line break."""
    return " ".join(str(value).split())


def _send(to_email, subject, html, plain):
    config = _get_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = _clean_header(subject)
    msg["From"] = f"SnapClass <{config['sender_email']}>"
    msg["To"] = _clean_header(to_email)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo()
        s.starttls()
        s.login(config["sender_email"], config["sender_password"])
        s.sendmail(config["sender_email"], to_email, msg.as_string())


def _fmt(ts):
    try:
        return datetime.fromisoformat(ts).strftime("%d %B %Y, %I:%M %p")
    except Exception:
        return ts


def send_student_attendance_email(student_name, student_email, subject_name, subject_code,
                                  teacher_name, timestamp):
    html, plain = T.student_attendance_email(student_name, subject_name, subject_code,
                                             teacher_name, _fmt(timestamp))
    _send(student_email, f"Attendance marked - {subject_name} ({subject_code})", html, plain)


def send_teacher_summary_email(teacher_name, teacher_email, subject_name, subject_code,
                               timestamp, present_students, total_enrolled):
    ft = _fmt(timestamp)
    html, plain = T.teacher_summary_email(teacher_name, subject_name, subject_code, ft,
                                          [s["name"] for s in present_students], total_enrolled)
    _send(teacher_email, f"Attendance summary - {subject_name} | {ft}", html, plain)


def send_all_attendance_emails(logs, subject_name, subject_code, teacher_name, teacher_email,
                               timestamp, all_enrolled_students):
    student_map = {s["student_id"]: s for s in all_enrolled_students}
    present_list, student_ok, student_fail = [], 0, 0

    for entry in logs:
        if not entry.get("is_present"):
            continue
        student = student_map.get(entry["student_id"])
        if not student:
            continue
        present_list.append(student)
        email = student.get("email")
        if not email:
            student_fail += 1
            continue
        try:
            send_student_attendance_email(student["name"], email, subject_name, subject_code,
                                          teacher_name, timestamp)
            student_ok += 1
        except Exception:
            log.exception("Student attendance email failed for student_id=%s", student.get("student_id"))
            student_fail += 1

    teacher_ok = False
    if teacher_email:
        try:
            send_teacher_summary_email(teacher_name, teacher_email, subject_name, subject_code,
                                       timestamp, present_list, len(all_enrolled_students))
            teacher_ok = True
        except Exception:
            log.exception("Teacher summary email failed")

    return student_ok, student_fail, teacher_ok
