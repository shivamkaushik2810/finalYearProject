from src.database.config import supabase
from src.services.authz import teacher_owns_subject
from src.services.db_utils import fetch_all
from src.services.pure_logic import classify, validate_thresholds
 
DEFAULTS = {'eligible_min': 75.0, 'condonable_min': 65.0}
 
 
def get_thresholds(subject_id):
    res = supabase.table('eligibility_settings').select('*').eq('subject_id', str(subject_id)).execute()
    if res.data:
        return {'eligible_min': float(res.data[0]['eligible_min']),
                'condonable_min': float(res.data[0]['condonable_min'])}
    return dict(DEFAULTS)
 
 
def set_thresholds(teacher_id, subject_id, eligible_min, condonable_min):
    if not teacher_owns_subject(teacher_id, subject_id):
        return False, "Not your subject."
    if not validate_thresholds(eligible_min, condonable_min):
        return False, "Need 0 < condonable <= eligible <= 100."
    supabase.table('eligibility_settings').upsert({
        'subject_id': str(subject_id), 'eligible_min': float(eligible_min),
        'condonable_min': float(condonable_min), 'updated_by': str(teacher_id),
    }).execute()
    return True, "Thresholds saved."
 
 
def subject_report(teacher_id, subject_id):
    if not teacher_owns_subject(teacher_id, subject_id):
        return []
    t = get_thresholds(subject_id)
    enrolled = fetch_all(lambda: supabase.table('subject_students')
                         .select('student_id, students(name, roll_no, section)')
                         .eq('subject_id', subject_id).order('student_id'))
    att = {str(r['student_id']): r for r in fetch_all(
        lambda: supabase.table('student_subject_attendance')
        .select('pair_key, student_id, total_classes, present_classes')
        .eq('subject_id', subject_id).order('pair_key'))}
    dec = {str(r['student_id']): r for r in fetch_all(
        lambda: supabase.table('condonation_decisions').select('*')
        .eq('subject_id', str(subject_id)).order('student_id'))}
    out = []
    for e in enrolled:
        sid = str(e['student_id'])
        s = e.get('students') or {}
        a = att.get(sid, {})
        total, present = int(a.get('total_classes') or 0), int(a.get('present_classes') or 0)
        pct = round(present / total * 100, 1) if total else 0.0
        status = classify(pct, t['eligible_min'], t['condonable_min']) if total else 'no_data'
        d = dec.get(sid)
        final = status
        if status == 'condonable' and d:
            final = 'condoned' if d['decision'] == 'condoned' else 'detained'
        out.append({'student_id': sid, 'name': s.get('name', '?'), 'roll_no': s.get('roll_no'),
                    'section': s.get('section'), 'total': total, 'present': present, 'pct': pct,
                    'status': status, 'decision': d['decision'] if d else None, 'final': final})
    out.sort(key=lambda r: (r['pct'], r['name']))
    return out
 
 
def set_condonation(teacher_id, subject_id, student_id, decision, reason):
    if not teacher_owns_subject(teacher_id, subject_id):
        return False, "Not your subject."
    if decision not in ('condoned', 'denied') or len((reason or '').strip()) < 5:
        return False, "Choose a decision and give a reason (5+ characters)."
    row = next((r for r in subject_report(teacher_id, subject_id) if r['student_id'] == str(student_id)), None)
    if not row or row['status'] != 'condonable':
        return False, "Only students in the condonable band can be condoned."
    supabase.table('condonation_decisions').upsert({
        'subject_id': str(subject_id), 'student_id': str(student_id),
        'decision': decision, 'reason': reason.strip(), 'decided_by': str(teacher_id),
    }).execute()
    return True, "Decision saved."
