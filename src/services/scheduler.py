import threading
from datetime import date
import streamlit as st


@st.cache_resource
def _state():
    return {"last_run": None, "lock": threading.Lock()}


def _run():
    try:
        from src.services.weekly_report_runner import send_weekly_reports_to_all_parents
        ok, bad = send_weekly_reports_to_all_parents()
        print(f"Weekly reports done: Success {ok}, Failed {bad}")
    except Exception as e:
        print(f"Weekly report error: {e}")


def check_and_send_weekly_reports():
    """Call from app.py. Mondays only, once per server process, non-blocking.
    The DB check inside the runner also prevents duplicate emails after restarts."""
    if date.today().weekday() != 0:
        return
    st_ = _state()
    today = str(date.today())
    if st_["last_run"] == today or not st_["lock"].acquire(blocking=False):
        return
    try:
        if st_["last_run"] != today:
            st_["last_run"] = today
            threading.Thread(target=_run, daemon=True).start()
    finally:
        st_["lock"].release()


def manual_send_weekly_reports():
    from src.services.weekly_report_runner import send_weekly_reports_to_all_parents
    return send_weekly_reports_to_all_parents()
