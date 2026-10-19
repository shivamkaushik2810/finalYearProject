import threading
from datetime import date

_lock = threading.Lock()
_state = {"last_run": None}   # module-level -> shared by ALL sessions in this process


def check_and_send_weekly_reports():
    """
    Call from app.py on every page load. On Mondays it starts ONE background job
    per process. Per-student idempotency (DB check) prevents duplicates even
    after a restart.
    """
    today = date.today()
    if today.weekday() != 0 or _state["last_run"] == today:
        return
    if not _lock.acquire(blocking=False):
        return
    _state["last_run"] = today

    def _job():
        try:
            from src.services.weekly_report_service import send_weekly_reports_to_all_parents
            print("📧 Sending weekly attendance reports to parents...")
            success, failed = send_weekly_reports_to_all_parents()
            print(f"Weekly reports done — Success: {success}, Failed: {failed}")
        except Exception as e:
            _state["last_run"] = None   # allow a retry on the next page load
            print(f"Weekly report error: {e}")
        finally:
            _lock.release()

    threading.Thread(target=_job, daemon=True).start()


def manual_send_weekly_reports():
    """Manual trigger from the teacher dashboard (skips students already reported)."""
    from src.services.weekly_report_service import send_weekly_reports_to_all_parents
    return send_weekly_reports_to_all_parents()
