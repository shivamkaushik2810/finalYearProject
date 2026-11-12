"""Pure, dependency-free helpers (no Streamlit / Supabase imports) so they can be unit-tested."""
import ipaddress
import math
import re
from datetime import date, datetime, time, timedelta
 
MAX_LEAVE_DAYS = 30
MAX_BACKDATE_DAYS = 30
MAX_DOC_BYTES = 2 * 1024 * 1024
_E164 = re.compile(r'^\+[1-9]\d{7,14}$')
 
 
def effective_pct(logs):
    """Attendance % where excused absences do not count against the student."""
    counted = [l for l in logs if l.get('is_present') or not l.get('is_excused')]
    if not counted:
        return 0.0
    present = sum(1 for l in counted if l.get('is_present'))
    return round(present / len(counted) * 100, 1)
 
 
def classify(pct, eligible_min=75.0, condonable_min=65.0):
    if pct >= eligible_min:
        return 'eligible'
    if pct >= condonable_min:
        return 'condonable'
    return 'detained'
 
 
def validate_thresholds(eligible_min, condonable_min):
    try:
        e, c = float(eligible_min), float(condonable_min)
    except (TypeError, ValueError):
        return False
    return 0 < c <= e <= 100
 
 
def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
 
 
def ip_allowed(ip, allowed):
    try:
        addr = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return False
    for entry in allowed or []:
        try:
            if addr in ipaddress.ip_network(str(entry).strip(), strict=False):
                return True
        except ValueError:
            continue
    return False
 
 
def location_ok(lat, lon, accuracy, fence_lat, fence_lon, radius_m):
    """True when the reported point is inside the fence (GPS accuracy tolerance capped at 100 m)."""
    if lat is None or lon is None:
        return False
    tol = min(max(float(accuracy or 0), 0.0), 100.0)
    return haversine_m(lat, lon, fence_lat, fence_lon) - tol <= radius_m
 
 
def normalize_phone(raw, default_cc='+91'):
    """Return E.164 string or None."""
    if not raw:
        return None
    s = re.sub(r'[\s\-().]', '', str(raw))
    if s.startswith('00'):
        s = '+' + s[2:]
    if re.fullmatch(r'[6-9]\d{9}', s):
        s = default_cc + s
    return s if _E164.match(s) else None
 
 
def parse_time(value):
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))
 
 
def within_slot(now_t, start, end, grace_min=10):
    to_m = lambda t: t.hour * 60 + t.minute
    return to_m(start) - grace_min <= to_m(now_t) <= to_m(end) + grace_min
 
 
def validate_leave_input(kind, start, end, reason, today=None):
    """Return an error string, or None when valid."""
    today = today or date.today()
    reason = (reason or '').strip()
    if kind not in ('leave', 'medical'):
        return 'Invalid request type.'
    if len(reason) < 5 or len(reason) > 500:
        return 'Reason must be 5-500 characters.'
    if end < start:
        return 'End date cannot be before start date.'
    if (end - start).days + 1 > MAX_LEAVE_DAYS:
        return f'A request can cover at most {MAX_LEAVE_DAYS} days.'
    if start < today - timedelta(days=MAX_BACKDATE_DAYS):
        return f'Cannot request leave older than {MAX_BACKDATE_DAYS} days.'
    return None
 
 
def doc_error(filename, data):
    """Validate an uploaded certificate by extension, size and magic bytes. None when OK."""
    name = (filename or '').lower()
    if len(data) == 0 or len(data) > MAX_DOC_BYTES:
        return 'File must be between 1 byte and 2 MB.'
    if name.endswith('.pdf') and data.startswith(b'%PDF'):
        return None
    if name.endswith(('.jpg', '.jpeg')) and data.startswith(b'\xff\xd8'):
        return None
    if name.endswith('.png') and data.startswith(b'\x89PNG'):
        return None
    return 'Only genuine PDF, JPG or PNG files are allowed.'
 
 
def csv_safe(value):
    """Neutralise spreadsheet formula injection."""
    s = '' if value is None else str(value)
    return "'" + s if s[:1] in ('=', '+', '-', '@', '\t', '\r') else s
 
 
def iso_week_key(d=None):
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'
