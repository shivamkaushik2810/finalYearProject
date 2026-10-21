import streamlit as st

COURSES = ['B.Tech', 'M.Tech', 'MCA', 'BCA', 'MBA', 'B.Sc', 'M.Sc']
YEARS = ['1', '2', '3', '4']


def _norm(v):
    return str(v).strip().lower() if v not in (None, '') else ''


def subject_label(s):
    bits = []
    if s.get('course'):
        bits.append(str(s['course']))
    if s.get('year'):
        bits.append(f"Year {s['year']}")
    if s.get('section'):
        bits.append(f"Sec {s['section']}")
    tail = f" [{' | '.join(bits)}]" if bits else ""
    return f"{s['name']} - {s['subject_code']}{tail}"


def subject_matches_student(sub, student):
    """A subject is open to a student unless course/year/section clearly differ.
    Blank values on either side never exclude."""
    for key in ('section', 'course', 'year'):
        sv, tv = _norm(sub.get(key)), _norm(student.get(key))
        if sv and tv and sv != tv:
            return False
    return True


def filter_rows(rows, key, fields=('course', 'year', 'section')):
    """Renders Course / Year / Section dropdowns built from the data; returns filtered rows."""
    cols = st.columns(len(fields))
    chosen = {}
    for col, f in zip(cols, fields):
        opts = sorted({str(r.get(f)).strip() for r in rows if r.get(f) not in (None, '')})
        with col:
            chosen[f] = st.selectbox(f.title(), ['All'] + opts, key=f"{key}_{f}")
    out = rows
    for f, v in chosen.items():
        if v != 'All':
            out = [r for r in out if _norm(r.get(f)) == _norm(v)]
    return out


def fetch_all(build, page=1000):
    """Pages through a Supabase query (default cap is 1000 rows). build() returns a fresh query."""
    rows, start = [], 0
    while True:
        chunk = build().range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def class_label(obj):
    """'B.Tech · Year 2 · Section B' for a student row or a subject row."""
    return (f"{obj.get('course') or '—'} · Year {obj.get('year') or '—'} · "
            f"Section {obj.get('section') or '—'}")


def can_enroll(sub, student):
    """Strict rule: course, year and section of the subject must equal the student's.
    A field left blank on the SUBJECT is not restricted; a blank on the STUDENT fails."""
    for key in ('course', 'year', 'section'):
        sv = _norm(sub.get(key))
        if not sv:
            continue
        tv = _norm(student.get(key))
        if not tv:
            return False, f"Your profile has no {key} set, so you cannot join this subject."
        if sv != tv:
            return False, f"This subject is only for {class_label(sub)}. Your class is {class_label(student)}."
    return True, ""


def cascade_filter(rows, key, fields=('course', 'year', 'section'), labels=None):
    """Course -> Year -> Section dropdowns where each one only offers options that exist
    for the earlier choices. Returns the rows that match."""
    labels = labels or {}
    pool = rows
    cols = st.columns(len(fields))
    for col, f in zip(cols, fields):
        opts = sorted({str(r.get(f)).strip() for r in pool if r.get(f) not in (None, '')})
        with col:
            v = st.selectbox(labels.get(f, f.title()), ['All'] + opts, key=f"{key}_{f}")
        if v != 'All':
            pool = [r for r in pool if _norm(r.get(f)) == _norm(v)]
    return pool
