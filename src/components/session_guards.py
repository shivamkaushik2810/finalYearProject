from src.components.client_location import get_client_ip, get_client_location
from src.services.schedule_service import check_session_allowed, check_scan_location, get_geofence


def guard_start_session(subject_id):
    """Timetable gate. Use before creating any QR / attendance session."""
    return check_session_allowed(subject_id)


def guard_scan(subject_id):
    """Location/IP gate. Use immediately before saving a student's QR/code scan."""
    fence = get_geofence(subject_id)
    if not fence or not fence.get('enabled'):
        return True, "ok"
    needs_gps = fence.get('latitude') is not None
    loc = get_client_location() if needs_gps else None
    return check_scan_location(subject_id, loc, get_client_ip(), fence=fence)
