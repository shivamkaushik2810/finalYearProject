import datetime as dt

import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.analytics.access import require_admin

PAGE = 1000
CHUNK = 40


def _fetch_all(make_query):
    out, start = [], 0
    while True:
        rows = make_query().range(start, start + PAGE - 1).execute().data or []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return out


def _norm(v):
    return (v or "").strip().upper()


@st.cache_data(ttl=60, show_spinner=False)
def _sections_cached():
    try:                                                    # SQL aggregation (analytics_sections)
        data = supabase.rpc("analytics_sections", {}).execute().data
        if isinstance(data, list):
            return {d["key"]: {"raw": sorted(d["raw"]), "count": d["count"]} for d in data}
    except Exception:
        pass
    rows = _fetch_all(lambda: supabase.table("students").select("student_id, section").order("student_id"))
    out = {}
    for r in rows:
        key = _norm(r.get("section"))
        if not key:
            continue
        e = out.setdefault(key, {"raw": set(), "count": 0})
        e["raw"].add(r.get("section"))
        e["count"] += 1
    return {k: {"raw": sorted(v["raw"]), "count": v["count"]} for k, v in sorted(out.items())}


@st.cache_data(ttl=60, show_spinner=False)
def _students_cached(raw_sections):
    rows = _fetch_all(lambda: supabase.table("students")
                      .select("student_id, name, roll_no, section, course, year")
                      .in_("section", list(raw_sections)).order("student_id"))
    rows.sort(key=lambda s: (str(s.get("roll_no") or ""), (s.get("name") or "").lower()))
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def _section_marks_cached(ids):
    out = []
    for i in range(0, len(ids), CHUNK):
        chunk = list(ids[i:i + CHUNK])
        out.extend(_fetch_all(lambda c=chunk: supabase.table("marks").select("*").in_("student_id", c).order("id")))
    return out


@st.cache_data(ttl=60, show_spinner=False)
def _section_agg_cached(section_key, subject_ids, start, end, exam_types):
    params = {"p_section": section_key,
              "p_subject_ids": list(subject_ids) if subject_ids is not None else None,
              "p_start": start.isoformat() if start else None,
              "p_end": end.isoformat() if end else None,
              "p_exam_types": list(exam_types) if exam_types else None}
    params = {k: v for k, v in params.items() if v is not None}     # JSON null would not become SQL NULL
    try:
        data = supabase.rpc("analytics_section_marks", params).execute().data
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    return pd.DataFrame(data, columns=["student_id", "subject_id", "obtained", "max_marks", "assessments"])


def get_sections():
    require_admin()
    return _sections_cached()


def get_students(section_key):
    require_admin()
    secs = _sections_cached()
    if section_key not in secs:
        raise ValueError("Unknown section.")
    return _students_cached(tuple(secs[section_key]["raw"]))


def _verify(section_key, student_id):
    student = next((s for s in get_students(section_key) if s["student_id"] == student_id), None)
    if not student:
        raise PermissionError("The student is not in the selected section.")
    return student


def _check_date(d, label):
    if d is None:
        return None
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    raise ValueError(f"Invalid {label} date.")


def get_enrolled_subjects(section_key, student_id):
    _verify(section_key, student_id)
    base = "subject_id, name, subject_code, section, teacher_id, teachers(name)"
    rows = None
    for cols in (base + ", academic_year, semester", base):          # works before the terms migration too
        try:
            rows = (supabase.table("subject_students").select(f"subject_id, subjects({cols})")
                    .eq("student_id", student_id).execute().data or [])
            break
        except Exception:
            if cols == base:
                raise
    out = []
    for r in rows:
        s = r.get("subjects") or {}
        if not s:
            continue
        out.append({"subject_id": s.get("subject_id", r.get("subject_id")), "name": s.get("name") or "Unknown",
                    "subject_code": s.get("subject_code") or "", "section": s.get("section"),
                    "teacher_id": s.get("teacher_id"), "faculty": (s.get("teachers") or {}).get("name") or "Unknown",
                    "academic_year": s.get("academic_year"), "semester": s.get("semester")})
    out.sort(key=lambda x: x["name"].lower())
    return out


def get_attendance(section_key, student_id, subject_ids=None, start=None, end=None):
    """subject_ids=None means all subjects (including ones the student has since left)."""
    _verify(section_key, student_id)
    start, end = _check_date(start, "start"), _check_date(end, "end")
    if start and end and start > end:
        raise ValueError("The start date is after the end date.")
    ids = None
    if subject_ids is not None:
        allowed = {s["subject_id"] for s in get_enrolled_subjects(section_key, student_id)}
        ids = [i for i in subject_ids if i in allowed]
        if not ids:
            return []

    def q(with_status):
        cols = "student_id, subject_id, is_present, timestamp"
        cols += ", status" if with_status else ""
        cols += ", subjects(name, subject_code, teacher_id, teachers(name))"
        x = supabase.table("attendance_logs").select(cols).eq("student_id", student_id).order("timestamp")
        if ids is not None:
            x = x.in_("subject_id", ids)
        if start:
            x = x.gte("timestamp", f"{start.isoformat()}T00:00:00")
        if end:
            x = x.lt("timestamp", f"{(end + dt.timedelta(days=1)).isoformat()}T00:00:00")
        return x

    try:
        return _fetch_all(lambda: q(True))
    except Exception:
        return _fetch_all(lambda: q(False))                  # status column not migrated yet


def get_marks(section_key, student_id):
    _verify(section_key, student_id)
    return _fetch_all(lambda: supabase.table("marks")
                      .select("*, subjects(name, subject_code, teacher_id, teachers(name))")
                      .eq("student_id", student_id).order("id"))


def get_section_marks_agg(section_key, subject_ids=None, start=None, end=None, exam_types=None):
    """Per student-and-subject marks totals computed in PostgreSQL. Returns None if the SQL function is missing."""
    require_admin()
    if section_key not in _sections_cached():
        raise ValueError("Unknown section.")
    return _section_agg_cached(section_key, tuple(subject_ids) if subject_ids is not None else None,
                               _check_date(start, "start"), _check_date(end, "end"),
                               tuple(exam_types) if exam_types else None)


def get_section_marks(section_key):
    """Fallback when the SQL function is not installed: raw rows for the whole section."""
    students = get_students(section_key)
    return _section_marks_cached(tuple(s["student_id"] for s in students))
