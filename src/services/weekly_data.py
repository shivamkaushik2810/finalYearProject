from collections import defaultdict
from datetime import timedelta
from src.database.config import supabase


def _fetch_all(query_builder, page=1000):
    """Supabase returns max 1000 rows per call, so page through results."""
    rows, start = [], 0
    while True:
        chunk = query_builder.range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def get_week_stats(week_start, week_end):
    """{(student_id, subject_id): {"total": n, "attended": n}} in ONE query."""
    end_exclusive = week_end + timedelta(days=1)  # include all of Sunday
    q = (supabase.table('attendance_logs')
         .select('student_id, subject_id, is_present')
         .gte('timestamp', str(week_start))
         .lt('timestamp', str(end_exclusive)))
    stats = defaultdict(lambda: {"total": 0, "attended": 0})
    for r in _fetch_all(q):
        key = (r['student_id'], r['subject_id'])
        stats[key]["total"] += 1
        if r.get('is_present'):
            stats[key]["attended"] += 1
    return stats


def get_enrollments_map():
    """{student_id: [subject dict, ...]} in ONE query."""
    q = supabase.table('subject_students').select(
        'student_id, subjects(subject_id, name, subject_code)')
    m = defaultdict(list)
    for r in _fetch_all(q):
        if r.get('subjects'):
            m[r['student_id']].append(r['subjects'])
    return m
