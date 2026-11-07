import logging
from src.database.config import supabase
from src.services.authz import teacher_owns_subject
from src.services.db_utils import fetch_all
 
log = logging.getLogger(__name__)
LOG_PK = 'id'   # change if attendance_logs uses a different primary key name
 
 
def _enrolled_map(subject_id):
    rows = fetch_all(lambda: supabase.table('subject_students')
                     .select('student_id, students(student_id, name, roll_no)')
                     .eq('subject_id', subject_id).order('student_id'))
    return {str(r['student_id']): (r.get('students') or {}) for r in rows}
 
 
def recent_sessions(teacher_id, subject_id, limit=30):
    if not teacher_owns_subject(teacher_id, subject_id):
        return []
    rows = supabase.table('attendance_logs').select('timestamp') \
        .eq('subject_id', subject_id).order('timestamp', desc=True).limit(3000).execute().data or []
    seen = []
    for r in rows:
        if r['timestamp'] not in seen:
            seen.append(r['timestamp'])
            if len(seen) >= limit:
                break
    return seen
 
 
def session_logs(teacher_id, subject_id, timestamp):
    if not teacher_owns_subject(teacher_id, subject_id):
        return []
    names = _enrolled_map(subject_id)
    rows = fetch_all(lambda: supabase.table('attendance_logs')
                     .select(f'{LOG_PK}, student_id, is_present, is_excused')
                     .eq('subject_id', subject_id).eq('timestamp', timestamp).order(LOG_PK))
    out = []
    for r in rows:
        s = names.get(str(r['student_id']), {})
        out.append({'log_id': str(r[LOG_PK]), 'name': s.get('name', '(unknown)'),
                    'roll_no': s.get('roll_no'), 'is_present': bool(r.get('is_present')),
                    'is_excused': bool(r.get('is_excused'))})
    out.sort(key=lambda x: x['name'])
    return out
 
 
def correct_attendance(teacher_id, log_id, new_present, reason):
    """Atomic DB function checks ownership, updates the record and writes the audit row."""
    if len((reason or '').strip()) < 5:
        return False, "Please enter a reason (at least 5 characters)."
    try:
        supabase.rpc('correct_attendance', {
            'p_log_id': str(log_id), 'p_teacher_id': str(teacher_id),
            'p_new_present': bool(new_present), 'p_reason': reason.strip(),
        }).execute()
        return True, "Attendance corrected and logged."
    except Exception as e:
        msg = getattr(e, 'message', '') or ''
        log.warning("correction failed: %s", type(e).__name__)
        known = ('Reason must', 'Record not found', 'No change')
        return False, msg if any(msg.startswith(k) for k in known) else "Could not apply the correction."
 
 
def list_audit(teacher_id, subject_id, limit=100):
    if not teacher_owns_subject(teacher_id, subject_id):
        return []
    names = _enrolled_map(subject_id)
    rows = supabase.table('attendance_audit_log').select('*') \
        .eq('subject_id', subject_id).order('changed_at', desc=True).limit(limit).execute().data or []
    for r in rows:
        r['student_name'] = names.get(str(r['student_id']), {}).get('name', '(unknown)')
    return rows
