from datetime import datetime

import streamlit as st

from src.components.charts import attendance_trend, subject_bars, weekly_heatmap
from src.services import attendance_stats as S
from src.ui.widgets import chip, esc, empty_state, stat_cards


def show_student_attendance_list(student_id):
    """Detailed attendance for one student: summary, charts, then per-subject sessions."""
    from src.database.config import supabase

    st.header("My attendance")

    res = supabase.table("attendance_logs") \
        .select("*, subjects(name, subject_code, section)") \
        .eq("student_id", student_id) \
        .order("timestamp", desc=True) \
        .execute()
    logs = res.data or []

    if not logs:
        empty_state("No attendance yet", "Your records appear here after your first class.")
        return

    subject_stats = {}
    for entry in logs:
        sub = entry.get("subjects") or {}
        sid = entry.get("subject_id")
        if not sid:
            continue
        row = subject_stats.setdefault(sid, {
            "name": sub.get("name", "Unknown"), "code": sub.get("subject_code", ""),
            "section": sub.get("section", ""), "total": 0, "present": 0, "absent": 0, "logs": []})
        row["total"] += 1
        if entry.get("is_present"):
            row["present"] += 1
        else:
            row["absent"] += 1
        row["logs"].append(entry)

    total = sum(s["total"] for s in subject_stats.values())
    present = sum(s["present"] for s in subject_stats.values())
    overall = round(present / total * 100) if total else 0
    kind = S.status_for(overall, total)[0]
    stat_cards([
        ("Total classes", total, ""),
        ("Present", present, "good"),
        ("Absent", total - present, "bad" if total - present else ""),
        ("Overall", f"{overall}%", {"good": "good", "avg": "avg", "risk": "bad"}.get(kind, "")),
    ])

    c1, c2 = st.columns(2)
    with c1:
        attendance_trend(logs)
    with c2:
        subject_bars([(s["name"], S.pct(s["present"], s["total"])) for s in subject_stats.values()])
    weekly_heatmap(logs)
    st.divider()

    for sid, stats in subject_stats.items():
        percent = round(stats["present"] / stats["total"] * 100) if stats["total"] else 0
        k, label, icon = S.status_for(percent, stats["total"])
        with st.expander(f"{icon} {stats['name']} ({stats['code']}): {percent}% ({label})"):
            m1, m2, m3 = st.columns(3)
            m1.metric("Total", stats["total"])
            m2.metric("Present", stats["present"])
            m3.metric("Absent", stats["absent"])

            if percent < 75:
                need = S.classes_needed(stats["present"], stats["total"])
                st.warning(f"Your attendance is below 75%. Attend the next {need} class(es) in a row to reach it.")

            st.write("**Sessions**")
            for entry in stats["logs"]:
                try:
                    dts = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "")).strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    dts = str(entry.get("timestamp", "Unknown"))
                ok = bool(entry.get("is_present"))
                bg, fg = ("#EAF3DE", "#27500A") if ok else ("#FCEBEB", "#791F1F")
                text = "\u2713 Present" if ok else "\u2717 Absent"
                st.markdown(
                    f"<div style='background:{bg};padding:8px 14px;border-radius:8px;margin:4px 0;"
                    f"display:flex;justify-content:space-between;'><span style='color:{fg}'>{esc(dts)}</span>"
                    f"<span style='color:{fg};font-weight:bold'>{text}</span></div>",
                    unsafe_allow_html=True)
