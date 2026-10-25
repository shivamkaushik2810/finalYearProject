import numpy as np
import pandas as pd
import streamlit as st
from src.database.config import supabase

PAGE = 1000


def _fetch_all(table, select="*", filters=None):
    """Fetch every row of a table (Supabase returns max 1000 per call)."""
    rows, start = [], 0
    while True:
        q = supabase.table(table).select(select)
        for col, val in (filters or {}).items():
            q = q.eq(col, val)
        res = q.range(start, start + PAGE - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < PAGE:
            break
        start += PAGE
    return rows


@st.cache_data(ttl=300, show_spinner="Loading analytics data...")
def load_core_frames():
    """Return (students, subjects, teachers, logs, marks) as DataFrames."""
    students = pd.DataFrame(_fetch_all(
        "students",
        "student_id,name,roll_no,section,year,course,email,parent_email,parent_name"))
    subjects = pd.DataFrame(_fetch_all("subjects", "*"))
    teachers = pd.DataFrame(_fetch_all("teachers", "teacher_id,name,username,email"))
    logs = pd.DataFrame(_fetch_all(
        "attendance_logs", "student_id,subject_id,timestamp,is_present"))
    marks = pd.DataFrame(_fetch_all(
        "marks", "student_id,subject_id,marks_obtained,max_marks,exam_type"))

    if not logs.empty:
        logs["is_present"] = logs["is_present"].fillna(False).astype(bool)
        logs["timestamp"] = pd.to_datetime(logs["timestamp"], errors="coerce")
    if not marks.empty:
        marks["pct"] = (marks["marks_obtained"].astype(float)
                        / marks["max_marks"].astype(float) * 100).round(1)
    return students, subjects, teachers, logs, marks


def student_attendance_summary(students, logs):
    """One row per student: total, present, pct."""
    if logs.empty:
        out = students.copy()
        out["total"], out["present"], out["pct"] = 0, 0, 0.0
        return out
    g = logs.groupby("student_id")["is_present"].agg(total="count", present="sum").reset_index()
    out = students.merge(g, on="student_id", how="left")
    out[["total", "present"]] = out[["total", "present"]].fillna(0).astype(int)
    total = pd.to_numeric(out["total"], errors="coerce").fillna(0).astype(float)
    present = pd.to_numeric(out["present"], errors="coerce").fillna(0).astype(float)
    safe_total = total.where(total > 0, 1.0)
    out["pct"] = pd.Series(np.where(total > 0, present / safe_total * 100, 0.0),
                           index=out.index).round(1)
    return out
