import logging
from datetime import datetime, timezone
import requests
import streamlit as st
 
from src.database.config import supabase
from src.services.pure_logic import normalize_phone
 
log = logging.getLogger(__name__)
 
 
def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default
 
 
def channel_mode():
    m = str(_secret('ALERT_CHANNEL', 'off')).lower()
    return m if m in ('whatsapp', 'sms') else 'off'
 
 
def send_message(raw_phone, body, mode=None):
    """Send via Twilio. Returns (ok, error_code). Never logs credentials or numbers."""
    mode = mode or channel_mode()
    if mode == 'off':
        return False, 'alerts disabled'
    to = normalize_phone(raw_phone)
    if not to:
        return False, 'invalid phone'
    sid, token = _secret('TWILIO_ACCOUNT_SID'), _secret('TWILIO_AUTH_TOKEN')
    sender = _secret('TWILIO_WHATSAPP_FROM' if mode == 'whatsapp' else 'TWILIO_FROM')
    if not (sid and token and sender):
        return False, 'twilio not configured'
    if mode == 'whatsapp':
        to = f'whatsapp:{to}'
        sender = sender if sender.startswith('whatsapp:') else f'whatsapp:{sender}'
    try:
        r = requests.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
            auth=(sid, token), data={'To': to, 'From': sender, 'Body': body[:1500]}, timeout=15)
    except requests.RequestException as e:
        return False, type(e).__name__
    return (True, '') if r.status_code < 300 else (False, f'twilio http {r.status_code}')
 
 
STALE_PENDING_MINUTES = 30
 
 
def _is_duplicate(e):
    return getattr(e, 'code', None) == '23505' or 'duplicate key' in str(e).lower()
 
 
def _age_minutes(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60
    except Exception:
        return 0.0          # unknown age -> treat as fresh (never double-send)
 
 
def _insert_claim(student_id, kind, channel, period_key):
    supabase.table('alert_log').insert({
        'student_id': str(student_id), 'kind': kind, 'channel': channel,
        'period_key': period_key, 'status': 'pending'}).execute()
 
 
def claim(student_id, kind, channel, period_key):
    """Reserve the notification (unique key blocks duplicates). False if already claimed.
    A 'pending' claim older than STALE_PENDING_MINUTES means a previous run died mid-send: take it over."""
    try:
        _insert_claim(student_id, kind, channel, period_key)
        return True
    except Exception as e:
        if not _is_duplicate(e):
            raise
    cur = supabase.table('alert_log').select('status, created_at') \
        .eq('student_id', str(student_id)).eq('kind', kind) \
        .eq('channel', channel).eq('period_key', period_key).execute().data
    if cur and cur[0].get('status') == 'pending' and _age_minutes(cur[0].get('created_at')) > STALE_PENDING_MINUTES:
        release(student_id, kind, channel, period_key)
        try:
            _insert_claim(student_id, kind, channel, period_key)
            return True
        except Exception as e:
            if not _is_duplicate(e):
                raise
    return False
 
 
def mark_sent(student_id, kind, channel, period_key):
    supabase.table('alert_log').update({'status': 'sent'}) \
        .eq('student_id', str(student_id)).eq('kind', kind) \
        .eq('channel', channel).eq('period_key', period_key).execute()
 
 
def release(student_id, kind, channel, period_key):
    """Failed send: free the slot so the next run can retry."""
    supabase.table('alert_log').delete() \
        .eq('student_id', str(student_id)).eq('kind', kind) \
        .eq('channel', channel).eq('period_key', period_key).execute()
