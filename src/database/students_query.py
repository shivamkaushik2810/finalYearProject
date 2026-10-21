from src.database.config import supabase

PAGE = 1000


def get_students_with_faces():
    """All students that have a face embedding (paginated, no 1000-row cap)."""
    rows, start = [], 0
    while True:
        res = supabase.table('students') \
            .select('student_id, name, face_embedding') \
            .not_.is_('face_embedding', 'null') \
            .range(start, start + PAGE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def get_student_by_id(student_id):
    res = supabase.table('students').select('*') \
        .eq('student_id', student_id).limit(1).execute()
    return res.data[0] if res.data else None


def get_teacher_subjects_only(teacher_id):
    """Only subjects created by this teacher."""
    res = supabase.table('subjects').select('*') \
        .eq('teacher_id', teacher_id).execute()
    return res.data or []
