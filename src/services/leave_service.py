import uuid
from datetime import datetime, timezone
 
from src.database.config import supabase
from src.services.authz import teacher_owns_subject
from src.services.pure_logic import validate_leave_input, doc_error, effective_pct  # noqa: F401
 
BUCKET = 'leave-docs'
_MIME = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}
 
 
def submit_leave(student_id, subject_id, kind, start, end, reason, doc_name=None, doc_bytes=None):
    err = validate_leave_input(kind, start, end, reason)
    if err:
        return False, err
    if doc_bytes is not None:
        err = doc_error(doc_name, doc_bytes)
        if err:
            return False, err
 
    enrolled = supabase.table('subject_students').select('id') \
        .eq('student_id', student_id).eq('subject_id', subject_id).execute()
    if not enrolled.data:
        return False, "You are not enrolled in this subject."
 
    overlap = supabase.table('leave_requests').select('id') \
        .eq('student_id', student_id).eq('subject_id', subject_id) \
        .in_('status', ['pending', 'approved']) \
        .lte('start_date', str(end)).gte('end_date', str(start)).execute()
    if overlap.data:
        return False, "You already have a pending/approved request for these dates."
 
    path = None
    if doc_bytes:
        ext = doc_name.rsplit('.', 1)[-1].lower()
        path = f"{student_id}/{uuid.uuid4().hex}.{ext}"
        try:
            supabase.storage.from_(BUCKET).upload(path, doc_bytes, {"content-type": _MIME[ext]})
        except Exception:
            return False, "Could not upload the certificate. Try again."
 
    supabase.table('leave_requests').insert({
        'student_id': student_id, 'subject_id': subject_id, 'kind': kind,
        'start_date': str(start), 'end_date': str(end),
        'reason': reason.strip(), 'document_path': path,
    }).execute()
    return True, "Request submitted."
 
 
def _attach(rows, with_students=False):
    """leave_requests has no foreign keys, so PostgREST cannot embed related rows; join in Python."""
    def lookup(table, key, cols, ids):
        ids, out = sorted({str(i) for i in ids}), {}
        for i in range(0, len(ids), 100):
            for r in supabase.table(table).select(cols).in_(key, ids[i:i + 100]).execute().data or []:
                out[str(r[key])] = r
        return out
    subs = lookup('subjects', 'subject_id', 'subject_id, name, subject_code', [r['subject_id'] for r in rows])
    studs = lookup('students', 'student_id', 'student_id, name, roll_no, section',
                   [r['student_id'] for r in rows]) if with_students else {}
    for r in rows:
        r['subjects'] = subs.get(str(r['subject_id']))
        if with_students:
            r['students'] = studs.get(str(r['student_id']))
    return rows
 
 
def list_for_student(student_id):
    res = supabase.table('leave_requests').select('*') \
        .eq('student_id', student_id).order('created_at', desc=True).limit(100).execute()
    return _attach(res.data or [])
 
 
def list_for_teacher(teacher_id, status='pending'):
    subs = supabase.table('subjects').select('subject_id').eq('teacher_id', teacher_id).execute()
    ids = [s['subject_id'] for s in (subs.data or [])]
    if not ids:
        return []
    q = supabase.table('leave_requests').select('*').in_('subject_id', ids)
    if status:
        q = q.eq('status', status)
    return _attach(q.order('created_at', desc=True).limit(200).execute().data or [], with_students=True)
 
 
def review_leave(request_id, teacher_id, approve, note=""):
    req = supabase.table('leave_requests').select('*').eq('id', request_id).execute()
    if not req.data:
        return False, "Request not found."
    req = req.data[0]
    if req['status'] != 'pending':
        return False, "Request was already reviewed."
    if not teacher_owns_subject(teacher_id, req['subject_id']):
        return False, "You can only review requests for your own subjects."
 
    upd = supabase.table('leave_requests').update({
        'status': 'approved' if approve else 'rejected',
        'reviewed_by': teacher_id,
        'review_note': (note or "")[:300],
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', request_id).eq('status', 'pending').execute()
    if not upd.data:
        return False, "Request was already reviewed."
 
    if approve:
        supabase.table('attendance_logs').update({'is_excused': True}) \
            .eq('student_id', req['student_id']).eq('subject_id', req['subject_id']) \
            .eq('is_present', False) \
            .gte('timestamp', f"{req['start_date']}T00:00:00") \
            .lte('timestamp', f"{req['end_date']}T23:59:59").execute()
    return True, "Approved." if approve else "Rejected."
 
 
def get_document_url(request_id, teacher_id):
    """Short-lived signed URL, only for the teacher who owns the subject."""
    req = supabase.table('leave_requests').select('subject_id, document_path') \
        .eq('id', request_id).execute()
    if not req.data or not req.data[0].get('document_path'):
        return None
    if not teacher_owns_subject(teacher_id, req.data[0]['subject_id']):
        return None
    res = supabase.storage.from_(BUCKET).create_signed_url(req.data[0]['document_path'], 300)
    return res.get('signedURL') or res.get('signedUrl')
