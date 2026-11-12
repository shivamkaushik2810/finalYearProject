import sys

from src.services.weekly_report_service import send_weekly_reports_to_all_parents

if __name__ == "__main__":
    ok, failed = send_weekly_reports_to_all_parents()
    print(f"weekly report: success={ok} failed={failed}")
    sys.exit(1 if failed and not ok else 0)
