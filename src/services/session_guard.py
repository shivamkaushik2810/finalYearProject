from datetime import datetime
from src.database.config import supabase

COOLDOWN_MINUTES = 40


def _parse(ts):
    # Timestamps are saved as local clock time; drop any tz suffix so we
    # compare like with like against datetime.now()
    dt = datetime.fromisoformat(str(ts).replace("Z", ""))
    return dt.replace(tzinfo=None)


def session_locked(subject_id, minutes=COOLDOWN_MINUTES):
    """Returns (locked: bool, remaining_seconds: int) for this subject."""
    try:
        res = supabase.table("attendance_logs")\
            .select("timestamp")\
            .eq("subject_id", subject_id)\
            .order("timestamp", desc=True)\
            .limit(1).execute()
        if not res.data:
            return False, 0
        last = _parse(res.data[0]["timestamp"])
        remaining = minutes * 60 - (datetime.now() - last).total_seconds()
        if remaining > 0:
            return True, int(remaining)
        return False, 0
    except Exception:
        return False, 0


def format_remaining(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s} sec"
