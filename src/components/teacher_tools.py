import pandas as pd
import streamlit as st

from src.components.leave_ui import teacher_leave_tab
from src.services import audit_service as audit
from src.services import eligibility_service as elig
from src.services import schedule_service as sched
from src.services.pure_logic import csv_safe

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _pick(subjects, key):
    if not subjects:
        st.info("Create a subject first.")
        return None
    opts = {f"{s['name']} - {s['subject_code']}": str(s['subject_id']) for s in subjects}
    return opts[st.selectbox("Subject", list(opts.keys()), key=key)]


def _corrections(subjects, teacher_id):
    sid = _pick(subjects, "corr_sub")
    if not sid:
        return
    sessions = audit.recent_sessions(teacher_id, sid)
    if not sessions:
        st.info("No attendance sessions yet.")
        return
    ts = st.selectbox("Session", sessions, key=f"corr_ts_{sid}")
    rows = audit.session_logs(teacher_id, sid, ts)
    if not rows:
        st.info("No records in this session.")
        return
    st.dataframe(pd.DataFrame([{
        "Name": r['name'], "Roll": r['roll_no'],
        "Status": "Present" if r['is_present'] else ("Excused" if r['is_excused'] else "Absent")}
        for r in rows]), hide_index=True, width='stretch')

    labels = {f"{r['name']} ({r['roll_no'] or 'N/A'})": r for r in rows}
    pick = st.selectbox("Student", list(labels.keys()), key=f"corr_stu_{sid}_{ts}")
    row = labels[pick]
    new_status = st.radio("Change to", ["Present", "Absent"],
                          index=1 if row['is_present'] else 0, horizontal=True,
                          key=f"corr_new_{row['log_id']}")
    reason = st.text_input("Reason (required)", key=f"corr_reason_{row['log_id']}")
    if st.button("Apply correction", type="primary", key=f"corr_btn_{row['log_id']}"):
        ok, msg = audit.correct_attendance(teacher_id, row['log_id'], new_status == "Present", reason)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    st.subheader("Audit log")
    hist = audit.list_audit(teacher_id, sid)
    if hist:
        st.dataframe(pd.DataFrame([{
            "When (UTC)": h['changed_at'], "Student": h['student_name'],
            "Old": "Present" if h['old_value'] else "Absent",
            "New": "Present" if h['new_value'] else "Absent",
            "By": h['changed_by'], "Reason": h['reason']} for h in hist]),
            hide_index=True, width='stretch')
    else:
        st.caption("No corrections yet.")


def _eligibility(subjects, teacher_id):
    sid = _pick(subjects, "elig_sub")
    if not sid:
        return
    t = elig.get_thresholds(sid)
    c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    e = c1.number_input("Eligible at or above (%)", 1.0, 100.0, t['eligible_min'], 1.0, key=f"el_e_{sid}")
    c = c2.number_input("Condonable at or above (%)", 1.0, 100.0, t['condonable_min'], 1.0, key=f"el_c_{sid}")
    if c3.button("Save", key=f"el_save_{sid}", type="primary"):
        ok, msg = elig.set_thresholds(teacher_id, sid, e, c)
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()

    rows = elig.subject_report(teacher_id, sid)
    if not rows:
        st.info("No enrolled students.")
        return
    m = st.columns(4)
    m[0].metric("Eligible", sum(r['final'] == 'eligible' for r in rows))
    m[1].metric("Condonable", sum(r['final'] == 'condonable' for r in rows))
    m[2].metric("Condoned", sum(r['final'] == 'condoned' for r in rows))
    m[3].metric("Detained", sum(r['final'] == 'detained' for r in rows))

    icon = {'eligible': '🟢 Eligible', 'condonable': '🟡 Condonable', 'condoned': '🟦 Condoned',
            'detained': '🔴 Detained', 'no_data': '⚪ No data'}
    df = pd.DataFrame([{"Name": r['name'], "Roll": r['roll_no'], "Section": r['section'],
                        "Present/Total": f"{r['present']}/{r['total']}", "%": r['pct'],
                        "Status": icon[r['final']]} for r in rows])
    st.dataframe(df, hide_index=True, width='stretch')
    safe = df.copy()
    for col in ("Name", "Roll", "Section"):
        safe[col] = safe[col].map(csv_safe)
    st.download_button("⬇️ Download CSV", safe.to_csv(index=False).encode(),
                       file_name="eligibility.csv", mime="text/csv", key=f"el_csv_{sid}")

    band = [r for r in rows if r['status'] == 'condonable']
    if band:
        st.subheader("Condonation decisions")
        labels = {f"{r['name']} ({r['pct']}%)": r for r in band}
        pick = labels[st.selectbox("Student", list(labels.keys()), key=f"cd_stu_{sid}")]
        decision = st.radio("Decision", ["condoned", "denied"], horizontal=True, key=f"cd_dec_{sid}")
        reason = st.text_input("Reason (required)", key=f"cd_reason_{sid}")
        if st.button("Save decision", key=f"cd_save_{sid}"):
            ok, msg = elig.set_condonation(teacher_id, sid, pick['student_id'], decision, reason)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()


def _schedule(subjects, teacher_id):
    sid = _pick(subjects, "sch_sub")
    if not sid:
        return
    st.subheader("🕒 Weekly class slots (IST)")
    for s in sched.list_slots(sid):
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.write(f"**{WEEKDAYS[s['weekday']]}** {str(s['start_time'])[:5]} - {str(s['end_time'])[:5]} "
                 f"(grace {s['grace_minutes']} min)")
        if c2.button("Remove", key=f"slot_del_{s['id']}"):
            ok, msg = sched.delete_slot(teacher_id, s['id'])
            (st.success if ok else st.error)(msg)
            st.rerun()
    a, b, c, d = st.columns(4)
    day = a.selectbox("Day", range(7), format_func=lambda i: WEEKDAYS[i], key=f"slot_day_{sid}")
    start = b.time_input("Start", key=f"slot_start_{sid}")
    end = c.time_input("End", key=f"slot_end_{sid}")
    grace = d.number_input("Grace (min)", 0, 60, 10, key=f"slot_grace_{sid}")
    if st.button("Add slot", key=f"slot_add_{sid}"):
        ok, msg = sched.add_slot(teacher_id, sid, day, start, end, grace)
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()

    st.divider()
    st.subheader("📍 QR scan location rules")
    st.caption("Students pass if they are on an allowed network OR inside the radius. "
               "Get coordinates from Google Maps (right-click the classroom, copy coordinates).")
    f = sched.get_geofence(sid) or {}
    enabled = st.checkbox("Enable location check", value=bool(f.get('enabled')), key=f"gf_en_{sid}")
    use_gps = st.checkbox("Use GPS radius", value=f.get('latitude') is not None, key=f"gf_gps_{sid}")
    lat = lon = None
    if use_gps:
        g1, g2, g3 = st.columns(3)
        lat = g1.number_input("Latitude", -90.0, 90.0, float(f.get('latitude') or 0.0), format="%.6f", key=f"gf_lat_{sid}")
        lon = g2.number_input("Longitude", -180.0, 180.0, float(f.get('longitude') or 0.0), format="%.6f", key=f"gf_lon_{sid}")
        radius = g3.number_input("Radius (m)", 20, 2000, int(f.get('radius_m') or 100), key=f"gf_rad_{sid}")
    else:
        radius = int(f.get('radius_m') or 100)
    ips = st.text_area("Allowed IPs / CIDR ranges (one per line, e.g. 203.0.113.0/24)",
                       value="\n".join(f.get('allowed_ips') or []), key=f"gf_ips_{sid}")
    if st.button("Save location rules", type="primary", key=f"gf_save_{sid}"):
        ok, msg = sched.save_geofence(teacher_id, sid, enabled, lat, lon, radius, ips.splitlines())
        (st.success if ok else st.error)(msg)


def teacher_more_tools(subjects, teacher_id):
    st.header("🧰 More Tools")
    t1, t2, t3, t4 = st.tabs(["Leave Requests", "Corrections & Audit", "Eligibility", "Schedule & Location"])
    with t1:
        teacher_leave_tab(teacher_id)
    with t2:
        _corrections(subjects, teacher_id)
    with t3:
        _eligibility(subjects, teacher_id)
    with t4:
        _schedule(subjects, teacher_id)
