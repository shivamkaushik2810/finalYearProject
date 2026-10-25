from datetime import datetime, timezone, timedelta
import streamlit as st
from src.database.config import supabase

FLAG_KEY = "feedback_enabled"
MIN_LEN = 5
MAX_LEN = 1000
MAX_PER_HOUR = 5
ROLES = ("student", "teacher")
CATEGORIES = ["Suggestion", "Bug / Problem", "Compliment", "Other"]


def _read_flag():
    res = supabase.table("app_settings").select("value") \
        .eq("key", FLAG_KEY).limit(1).execute()
    return bool(res.data) and res.data[0]["value"] == "true"


@st.cache_data(ttl=5, show_spinner=False)
def is_feedback_enabled():
    """Cached flag for UI visibility. Fails closed (hidden) on any error."""
    try:
        return _read_flag()
    except Exception as e:
        print(f"Feedback flag read failed: {type(e).__name__}")
        return False


def set_feedback_enabled(enabled: bool):
    supabase.table("app_settings").upsert(
        {"key": FLAG_KEY,
         "value": "true" if enabled else "false",
         "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="key"
    ).execute()
    is_feedback_enabled.clear()


def submit_feedback(role, sender_id, sender_name, category, message):
    """Returns (ok, message). Re-checks the flag uncached on every submit."""
    try:
        if role not in ROLES:
            return False, "Invalid sender role."
        if not sender_id:
            return False, "You must be logged in to send feedback."
        if category not in CATEGORIES:
            return False, "Invalid category."
        message = (message or "").strip()
        if len(message) < MIN_LEN:
            return False, f"Feedback must be at least {MIN_LEN} characters."
        if len(message) > MAX_LEN:
            return False, f"Feedback must be at most {MAX_LEN} characters."
        if not _read_flag():
            return False, "Feedback is currently disabled."

        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent = supabase.table("feedback").select("id", count="exact") \
            .eq("sender_role", role).eq("sender_id", str(sender_id)) \
            .gte("created_at", since).execute()
        if (recent.count or 0) >= MAX_PER_HOUR:
            return False, "Too many submissions. Please try again later."

        supabase.table("feedback").insert({
            "sender_role": role,
            "sender_id":   str(sender_id),
            "sender_name": sender_name,
            "category":    category,
            "message":     message,
        }).execute()
        return True, "Thank you! Your feedback was sent."
    except Exception as e:
        print(f"Feedback submit failed: {type(e).__name__}")
        return False, "Could not send feedback. Please try again."


def list_feedback_meta(limit=100):
    """Admin list WITHOUT message text (message is revealed only on read)."""
    res = supabase.table("feedback") \
        .select("id, sender_role, sender_name, category, created_at") \
        .order("created_at", desc=True).limit(limit).execute()
    return res.data or []


def read_and_delete_feedback(feedback_id):
    """
    Atomic read+delete: the DELETE returns the removed row, so only one
    admin session can ever obtain a given message. Returns row or None.
    """
    res = supabase.table("feedback").delete().eq("id", feedback_id).execute()
    return res.data[0] if res.data else None
