from src.database.config import supabase
 
 
def teacher_owns_subject(teacher_id, subject_id):
    if not teacher_id or not subject_id:
        return False
    res = supabase.table('subjects').select('subject_id') \
        .eq('subject_id', subject_id).eq('teacher_id', teacher_id).limit(1).execute()
    return bool(res.data)
