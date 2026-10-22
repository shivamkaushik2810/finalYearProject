import os
import sys
from pathlib import Path

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.mail_pool import pooled_smtp
from src.services.weekly_report_service import send_weekly_parent_email
from src.services.weekly_report_runner import last_full_week

if len(sys.argv) < 2:
    raise SystemExit("usage: python scripts/test_email.py your.own@gmail.com")

to = sys.argv[1]
week_start, week_end = last_full_week()

with pooled_smtp():
    send_weekly_parent_email(
        parent_name="Test Parent", parent_email=to,
        student_name="Test Student", roll_no="123", section="A",
        subject_reports=[
            {'subject_name': 'Maths', 'subject_code': 'M101', 'total': 5,
             'attended': 4, 'absent': 1, 'attendance_pct': 80.0},
            {'subject_name': 'Physics', 'subject_code': 'P101', 'total': 4,
             'attended': 1, 'absent': 3, 'attendance_pct': 25.0},
        ],
        week_start=week_start, week_end=week_end,
    )
print(f"✓ Gmail accepted the message for {to}. Now check that inbox (and Spam).")
