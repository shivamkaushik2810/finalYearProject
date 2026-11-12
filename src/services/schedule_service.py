from datetime import datetime
from zoneinfo import ZoneInfo
 
from src.database.config import supabase
from src.services.authz import teacher_owns_subject
from src.services.pure_logic import within_slot, parse_time, ip_allowed, location_ok
import ipaddress
 
IST = ZoneInfo("Asia/Kolkata")
ENFORCE_WHEN_NO_SLOTS = False   # True = subjects without a timetable cannot start sessions
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
 
 
def list_slots(subject_id):
    return supabase.table('subject_slots').select('*').eq('subject_id', str(subject_id)) \
        .order('weekday').order('start_time').execute().data or []
 
 
def add_slot(teacher_id, subject_id, weekday, start, end, grace=10):
    if not teacher_owns_subject(teacher_id, subject_id):
        return False, "Not your subject."
    if not (0 <= int(weekday) <= 6) or not (0 <= int(grace) <= 60) or end <= start:
        return False, "Invalid slot (end must be after start; grace 0-60 min)."
    supabase.table('subject_slots').insert({
        'subject_id': str(subject_id), 'weekday': int(weekday),
        'start_time': start.strftime('%H:%M:%S'), 'end_time': end.strftime('%H:%M:%S'),
        'grace_minutes': int(grace)}).execute()
    return True, "Slot added."
 
 
def delete_slot(teacher_id, slot_id):
    res = supabase.table('subject_slots').select('subject_id').eq('id', slot_id).execute()
    if not res.data or not teacher_owns_subject(teacher_id, res.data[0]['subject_id']):
        return False, "Not allowed."
    supabase.table('subject_slots').delete().eq('id', slot_id).execute()
    return True, "Slot removed."
 
 
def check_session_allowed(subject_id, now=None):
    """(ok, message). Call BEFORE creating an attendance/QR session."""
    now = now or datetime.now(IST)
    all_slots = list_slots(subject_id)
    if not all_slots:
        return (not ENFORCE_WHEN_NO_SLOTS,
                "No timetable set for this subject." if ENFORCE_WHEN_NO_SLOTS
                else "No timetable set - session allowed.")
    today = [s for s in all_slots if s['weekday'] == now.weekday()]
    for s in today:
        if within_slot(now.time(), parse_time(s['start_time']), parse_time(s['end_time']),
                       int(s.get('grace_minutes') or 0)):
            return True, "Within scheduled slot."
    if not today:
        return False, f"No class scheduled for this subject on {DAYS[now.weekday()]}."
    spans = ", ".join(f"{str(s['start_time'])[:5]}-{str(s['end_time'])[:5]}" for s in today)
    return False, f"Outside the scheduled slot today ({spans} IST)."
 
 
def get_geofence(subject_id):
    res = supabase.table('subject_geofence').select('*').eq('subject_id', str(subject_id)).execute()
    return res.data[0] if res.data else None
 
 
def save_geofence(teacher_id, subject_id, enabled, lat, lon, radius_m, ips):
    if not teacher_owns_subject(teacher_id, subject_id):
        return False, "Not your subject."
    if not (20 <= int(radius_m) <= 2000):
        return False, "Radius must be 20-2000 m."
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False, "Invalid coordinates."
    clean = []
    for entry in ips:
        entry = entry.strip()
        if not entry:
            continue
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            return False, f"Invalid IP/CIDR: {entry}"
        clean.append(entry)
    if enabled and not clean and lat is None:
        return False, "Enable needs coordinates and/or allowed IP ranges."
    supabase.table('subject_geofence').upsert({
        'subject_id': str(subject_id), 'enabled': bool(enabled),
        'latitude': lat, 'longitude': lon, 'radius_m': int(radius_m),
        'allowed_ips': clean, 'updated_by': str(teacher_id)}).execute()
    return True, "Location rules saved."
 
 
def check_scan_location(subject_id, loc, ip, fence=None):
    """loc = (lat, lon, accuracy) or None. Passes on allowed network OR inside radius."""
    fence = fence or get_geofence(subject_id)
    if not fence or not fence.get('enabled'):
        return True, "Location check not required."
    if fence.get('allowed_ips') and ip_allowed(ip, fence['allowed_ips']):
        return True, "Classroom network verified."
    if fence.get('latitude') is not None and fence.get('longitude') is not None:
        if not loc:
            return False, "Location needed: allow location access in your browser and retry."
        lat, lon, acc = loc
        if location_ok(lat, lon, acc, fence['latitude'], fence['longitude'], fence['radius_m']):
            return True, "Location verified."
        return False, "You appear to be outside the classroom."
    return False, "You are not on the classroom network."
