from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist_iso():
    """Timezone-aware IST timestamp for saving to the database."""
    return datetime.now(IST).isoformat(timespec="seconds")


def to_ist(ts):
    """Parse a stored timestamp (naive = UTC) and return an IST datetime."""
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(IST)
