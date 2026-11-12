from src.database.config import supabase
 
MAX_EMBEDDINGS = 5
 
 
def all_embeddings(student):
    """Primary embedding + extra angles, de-duplicated."""
    embs = []
    primary = student.get('face_embedding')
    if primary:
        embs.append(primary)
    for e in (student.get('face_embeddings') or []):
        if e and e not in embs:
            embs.append(e)
    return embs
 
 
def add_face_angle(student_id, embedding):
    """Append one embedding (list of 128 floats). Returns (ok, message, updated_student_row)."""
    if not embedding or len(embedding) != 128:
        return False, "Invalid face embedding.", None
    res = supabase.table('students').select('*').eq('student_id', student_id).execute()
    if not res.data:
        return False, "Student not found.", None
    row = res.data[0]
    current = all_embeddings(row)
    if len(current) >= MAX_EMBEDDINGS:
        return False, f"Maximum {MAX_EMBEDDINGS} face samples reached.", row
    extras = list(row.get('face_embeddings') or [])
    extras.append(embedding)
    upd = supabase.table('students').update({'face_embeddings': extras}) \
        .eq('student_id', student_id).execute()
    new_row = (upd.data or [row])[0]
    return True, f"Saved ({len(current) + 1}/{MAX_EMBEDDINGS} samples).", new_row
