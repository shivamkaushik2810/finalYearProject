from datetime import datetime, timezone
import streamlit as st
from src.database.config import supabase
from src.utils.time_utils import IST

FLAG_KEY = "feedback_enabled"
MIN_LEN = 5
MAX_LEN = 1000
ROLES = ("student", "teacher")
CATEGORIES = ["Suggestion", "Bug / Problem", "Compliment", "Other"]
ALREADY_MSG = "You have already sent feedback today. You can send again tomorrow."


def today_ist():
    """Today's date in IST as YYYY-MM-DD."""
    return datetime.now(IST).date().isoformat()


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


@st.cache_data(ttl=30, show_spinner=False)
def has_sent_today(role, sender_id, day):
    """UI hint only (cached). The real limit is enforced in submit_feedback.
    `day` is part of the cache key so it rolls over at midnight IST."""
    try:
        res = supabase.table("feedback_sent_log").select("sender_id") \
            .eq("sender_role", role).eq("sender_id", str(sender_id)) \
            .eq("sent_day", day).limit(1).execute()
        return bool(res.data)
    except Exception as e:
        print(f"Feedback daily check failed: {type(e).__name__}")
        return False


def _is_duplicate(err):
    text = str(err).lower()
    return "23505" in text or "duplicate" in text


def submit_feedback(role, sender_id, sender_name, category, message):
    """Returns (ok, message). One submission per user per IST day, enforced
    by the primary key of feedback_sent_log (safe against double clicks)."""
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

        day = today_ist()
        log_row = {"sender_role": role, "sender_id": str(sender_id), "sent_day": day}

        # Claim today's slot first; a duplicate means already sent.
        try:
            supabase.table("feedback_sent_log").insert(log_row).execute()
        except Exception as e:
            if _is_duplicate(e):
                has_sent_today.clear()
                return False, ALREADY_MSG
            raise

        try:
            supabase.table("feedback").insert({
                "sender_role": role,
                "sender_id":   str(sender_id),
                "sender_name": sender_name,
                "category":    category,
                "message":     message,
            }).execute()
        except Exception:
            # Release the slot so the user can retry a failed send.
            try:
                supabase.table("feedback_sent_log").delete() \
                    .eq("sender_role", role).eq("sender_id", str(sender_id)) \
                    .eq("sent_day", day).execute()
            except Exception as cleanup_err:
                print(f"Feedback slot release failed: {type(cleanup_err).__name__}")
            raise

        has_sent_today.clear()
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
