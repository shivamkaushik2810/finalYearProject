from datetime import datetime

import streamlit as st

from src.database.attendance_status import eligible
from src.services.attendance_summary import summarize, scope_label
from src.services.attendance_stats import classes_needed


def show_student_attendance_list(student_id):
    from src.database.config import supabase

    st.header("📋 My Attendance Records")
    res = supabase.table('attendance_logs')\
        .select('*, subjects(name, subject_code, section)')\
        .eq('student_id', student_id)\
        .order('timestamp', desc=True)\
        .execute()
    logs = res.data or []
    if not logs:
        st.info("No attendance records found yet.")
        return

    subject_stats = {}
    for log in logs:
        sid = log.get('subject_id')
        if not sid:
            continue
        sub = log.get('subjects') or {}
        entry = subject_stats.setdefault(sid, {
            'name': sub.get('name', 'Unknown'), 'code': sub.get('subject_code', ''), 'logs': []})
        entry['logs'].append(log)
    for entry in subject_stats.values():
        entry['sum'] = summarize(entry['logs'])

    overall = summarize(logs)
    pct_txt = f"{overall['pct']:.0f}%" if overall['pct'] is not None else "No data"
    if overall['pct'] is None:
        color = "⚪"
    elif overall['pct'] >= 75:
        color = "🟢"
    elif overall['pct'] >= 50:
        color = "🟡"
    else:
        color = "🔴"

    st.caption(f"Scope: {scope_label()}. Cancelled classes are not counted. "
               "Excused absences are left out of the percentage.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Classes", overall['total'])
    c2.metric("✅ Present", overall['present'])
    c3.metric("❌ Absent", overall['absent'])
    c4.metric("Overall", f"{color} {pct_txt}")
    st.divider()

    for entry in subject_stats.values():
        s = entry['sum']
        if s['pct'] is None:
            continue
        icon = "🟢" if s['pct'] >= 75 else "🟡" if s['pct'] >= 50 else "🔴"
        with st.expander(f"{icon} {entry['name']} ({entry['code']}) — {s['pct']:.0f}% attendance"):
            a, b, c = st.columns(3)
            a.metric("Total", s['total'])
            b.metric("✅ Present", s['present'])
            c.metric("❌ Absent", s['absent'])
            if s['pct'] < 75:
                st.warning(f"⚠️ Below 75%. Attend the next "
                           f"{classes_needed(s['present'], s['total'])} class(es) in a row to reach it.")
            st.divider()
            st.write("**Session-wise Details:**")
            for log in sorted(entry['logs'], key=lambda l: str(l.get('timestamp')), reverse=True):
                if str(log.get('status') or '').lower() == 'cancelled':
                    continue
                try:
                    dts = datetime.fromisoformat(str(log['timestamp']).replace('Z', '')).strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    dts = log.get('timestamp', 'Unknown')
                if log.get('is_present'):
                    label, bg, fg = "✅ Present", "#d4edda", "#155724"
                elif log.get('is_excused'):
                    label, bg, fg = "🟦 Excused", "#d6eaf8", "#1b4f72"
                else:
                    label, bg, fg = "❌ Absent", "#f8d7da", "#721c24"
                st.markdown(
                    f"<div style='background:{bg};padding:8px 14px;border-radius:8px;margin:4px 0;"
                    f"display:flex;justify-content:space-between;'>"
                    f"<span style='color:{fg};font-size:14px;'>📅 {dts}</span>"
                    f"<span style='color:{fg};font-weight:bold;font-size:14px;'>{label}</span></div>",
                    unsafe_allow_html=True)
