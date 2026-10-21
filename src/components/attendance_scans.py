from src.database.config import supabase

METHODS = [("qr", "QR"), ("nfc", "NFC"), ("voice", "Voice"), ("photo", "Photo")]
METHOD_LABEL = dict(METHODS)


def open_session(subject_id):
    """The open (not yet confirmed) attendance session of a subject, or None."""
    res = supabase.table('attendance_sessions').select('*')\
        .eq('subject_id', subject_id).eq('is_active', True)\
        .order('expires_at', desc=True).limit(1).execute()
    return res.data[0] if res.data else None


def session_id_of(session):
    return session.get('id') if session.get('id') is not None else session.get('session_id')


def get_scans(session_id):
    res = supabase.table('attendance_scans')\
        .select('student_id, method, scanned_at')\
        .eq('session_id', session_id).execute()
    return res.data or []


def record_scan(session_id, student_id, subject_id, method):
    """One pending entry. Returns (ok, message). Same student + same method twice is ignored."""
    try:
        supabase.table('attendance_scans').insert({
            'session_id': session_id, 'student_id': student_id,
            'subject_id': subject_id, 'method': method}).execute()
        return True, "recorded"
    except Exception as e:
        if 'duplicate' in str(e).lower() or '23505' in str(e):
            return False, "already recorded with this method"
        raise


def record_many(session_id, subject_id, student_ids, method):
    """Bulk version for photo / voice results. Returns how many were newly added."""
    have = {r['student_id'] for r in get_scans(session_id) if r.get('method') == method}
    rows = [{'session_id': session_id, 'student_id': s, 'subject_id': subject_id, 'method': method}
            for s in dict.fromkeys(student_ids) if s not in have]
    for i in range(0, len(rows), 500):
        supabase.table('attendance_scans').insert(rows[i:i + 500]).execute()
    return len(rows)
