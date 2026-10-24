from src.database.config import supabase

PAGE = 1000  # Supabase returns max 1000 rows per request


def paginate(build):
    """build() must return a fresh query builder each call."""
    rows, start = [], 0
    while True:
        batch = build().range(start, start + PAGE - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        start += PAGE


def chunks(seq, n=150):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_students_with_parents():
    """No embeddings pulled, only the columns the report needs."""
    return paginate(lambda: (
        supabase.table("students")
        .select("student_id,name,email,roll_no,section,parent_name,parent_email")
        .not_.is_("parent_email", "null")
        .neq("parent_email", "")
        .order("student_id")
    ))


def get_student_by_id(student_id):
    res = supabase.table("students").select("*").eq("student_id", student_id).limit(1).execute()
    return res.data[0] if res.data else None


def get_enrollments_for_students(student_ids):
    """Returns {student_id: [subject_dict, ...]} in few queries."""
    out = {}
    for chunk in chunks(student_ids):
        rows = paginate(lambda c=chunk: (
            supabase.table("subject_students")
            .select("student_id, subjects(subject_id,name,subject_code)")
            .in_("student_id", c)
            .order("id")
        ))
        for r in rows:
            if r.get("subjects"):
                out.setdefault(r["student_id"], []).append(r["subjects"])
    return out


def get_logs_between(start_dt, end_dt):
    """start_dt inclusive, end_dt exclusive (datetime objects)."""
    return paginate(lambda: (
        supabase.table("attendance_logs")
        .select("student_id,subject_id,is_present")
        .gte("timestamp", _ts(start_dt))
        .lt("timestamp", _ts(end_dt))
        .order("timestamp").order("student_id").order("subject_id")
    ))


def get_subject_attendance_summary(subject_id):
    """Returns {student_id: (total, present)} using ONE query for the subject."""
    rows = paginate(lambda: (
        supabase.table("attendance_logs")
        .select("student_id,is_present,timestamp")
        .eq("subject_id", subject_id)
        .order("timestamp").order("student_id")
    ))
    out = {}
    for r in rows:
        t, p = out.get(r["student_id"], (0, 0))
        out[r["student_id"]] = (t + 1, p + (1 if r.get("is_present") else 0))
    return out
