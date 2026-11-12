import re
from datetime import datetime
from zoneinfo import ZoneInfo
from src.utils.time_utils import now_ist_wallclock, today_ist_start

IST = ZoneInfo("Asia/Kolkata")


def test_wallclock_format_and_value():
    s = now_ist_wallclock()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s)
    ist_now = datetime.now(IST).replace(tzinfo=None)
    assert abs((datetime.fromisoformat(s) - ist_now).total_seconds()) < 5


def test_today_start_is_ist_midnight():
    s = today_ist_start()
    assert s.endswith("T00:00:00")
    assert s[:10] == datetime.now(IST).strftime("%Y-%m-%d")
