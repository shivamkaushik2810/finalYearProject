import streamlit as st
from datetime import datetime
from src.database.attendance_status import eligible


def show_student_attendance_list(student_id):
    """Show detailed attendance list for student"""
    from src.database.config import supabase

    st.header("📋 My Attendance Records")

    # Get all attendance logs with subject info
    res = supabase.table('attendance_logs')\
        .select('*, subjects(name, subject_code, section)')\
        .eq('student_id', student_id)\
        .order('timestamp', desc=True)\
        .execute()

    logs = eligible(res.data)

    if not logs:
        st.info("No attendance records found yet.")
        return

    # Build stats per subject
    subject_stats = {}
    for log in logs:
        sub  = log.get('subjects', {})
        sid  = log.get('subject_id')
        if not sid:
            continue
        if sid not in subject_stats:
            subject_stats[sid] = {
                'name':    sub.get('name', 'Unknown'),
                'code':    sub.get('subject_code', ''),
                'section': sub.get('section', ''),
                'total':   0,
                'present': 0,
                'absent':  0,
                'logs':    []
            }
        subject_stats[sid]['total'] += 1
        if log.get('is_present'):
            subject_stats[sid]['present'] += 1
        else:
            subject_stats[sid]['absent'] += 1
        subject_stats[sid]['logs'].append(log)

    # Overall stats
    total_classes  = sum(s['total']   for s in subject_stats.values())
    total_present  = sum(s['present'] for s in subject_stats.values())
    total_absent   = sum(s['absent']  for s in subject_stats.values())
    overall_pct    = round((total_present / total_classes) * 100) if total_classes > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Classes", total_classes)
    with col2:
        st.metric("✅ Present", total_present)
    with col3:
        st.metric("❌ Absent", total_absent)
    with col4:
        color = "🟢" if overall_pct >= 75 else "🟡" if overall_pct >= 50 else "🔴"
        st.metric("Overall", f"{color} {overall_pct}%")

    st.divider()

    # Subject wise breakdown
    for sid, stats in subject_stats.items():
        pct   = round((stats['present'] / stats['total']) * 100) if stats['total'] > 0 else 0
        color = "🟢" if pct >= 75 else "🟡" if pct >= 50 else "🔴"

        with st.expander(
            f"{color} {stats['name']} ({stats['code']}) — {pct}% attendance",
            expanded=False
        ):
            # Subject stats
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total", stats['total'])
            with c2:
                st.metric("✅ Present", stats['present'])
            with c3:
                st.metric("❌ Absent", stats['absent'])

            # Warning if low attendance
            if pct < 75:
                st.warning(f"⚠️ Your attendance is below 75%! You need to attend more classes.")

            st.divider()
            st.write("**Session-wise Details:**")

            # Show each session
            for log in stats['logs']:
                try:
                    dt  = datetime.fromisoformat(log['timestamp'].replace('Z', ''))
                    dts = dt.strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    dts = log.get('timestamp', 'Unknown')

                is_present = log.get('is_present', False)
                status     = "✅ Present" if is_present else "❌ Absent"
                bg_color   = "#d4edda" if is_present else "#f8d7da"
                txt_color  = "#155724" if is_present else "#721c24"

                st.markdown(
                    f"""<div style='background:{bg_color};padding:8px 14px;
                    border-radius:8px;margin:4px 0;
                    display:flex;justify-content:space-between;'>
                    <span style='color:{txt_color};font-size:14px;'>📅 {dts}</span>
                    <span style='color:{txt_color};font-weight:bold;font-size:14px;'>{status}</span>
                    </div>""",
                    unsafe_allow_html=True
                )
