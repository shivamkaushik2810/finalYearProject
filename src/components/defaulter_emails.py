import pandas as pd
import streamlit as st
from src.services.thresholds import ATTENDANCE_TARGET, ATTENDANCE_WARN
from src.database.analytics_queries import load_core_frames, student_attendance_summary
from src.services.defaulter_email_service import send_defaulter_report, send_defaulter_family_report


def _build_report(student_id, logs, subjects, marks):
    sub_map = subjects.set_index("subject_id")["name"].to_dict() if not subjects.empty else {}
    s_logs = logs[logs["student_id"] == student_id] if not logs.empty else logs

    subject_rows = []
    if not s_logs.empty:
        for sid, g in s_logs.groupby("subject_id"):
            att, tot = int(g["is_present"].sum()), len(g)
            subject_rows.append({"subject": sub_map.get(sid, "Unknown"),
                                 "attended": att, "total": tot,
                                 "pct": round(att / tot * 100, 1)})

    session_rows = []
    monthly = pd.DataFrame(columns=["month", "pct"])
    if not s_logs.empty:
        recent = s_logs.sort_values("timestamp", ascending=False).head(25)
        session_rows = [(t.strftime("%d %b %Y, %I:%M %p"), sub_map.get(sid, "Unknown"),
                         "Present" if p else "Absent")
                        for t, sid, p in zip(recent["timestamp"], recent["subject_id"],
                                             recent["is_present"])]
        m = s_logs.dropna(subset=["timestamp"]).copy()
        m["month"] = m["timestamp"].dt.strftime("%Y-%m")
        monthly = (m.groupby("month")["is_present"].mean() * 100).round(1).reset_index()
        monthly.columns = ["month", "pct"]

    marks_rows = []
    if not marks.empty:
        sm = marks[marks["student_id"] == student_id]
        marks_rows = [{"subject": sub_map.get(r["subject_id"], "Unknown"),
                       "exam": r["exam_type"], "obtained": r["marks_obtained"],
                       "max": r["max_marks"], "pct": r["pct"]} for _, r in sm.iterrows()]
    return subject_rows, session_rows, marks_rows, monthly


def show_defaulter_email_panel(teacher_id=None, key="def"):
    """teacher_id=None -> admin (all subjects); else only that teacher's subjects."""
    if teacher_id is None:
        if not st.session_state.get("admin_data"):
            st.error("Admin login required.")
            return
    elif (st.session_state.get("teacher_data") or {}).get("teacher_id") != teacher_id:
        st.error("Not authorised.")
        return
    st.subheader("🚨 Defaulter Students — Parent Alerts")

    students, subjects, _, logs, marks = load_core_frames()
    if students.empty or logs.empty:
        st.info("No attendance data yet.")
        return

    if teacher_id is not None and not subjects.empty:
        own = subjects[subjects["teacher_id"] == teacher_id]["subject_id"].tolist()
        logs = logs[logs["subject_id"].isin(own)]
        students = students[students["student_id"].isin(logs["student_id"].unique())]
        subjects = subjects[subjects["subject_id"].isin(own)]
        marks = marks[marks["subject_id"].isin(own)] if not marks.empty else marks

    c1, c2, c3 = st.columns(3)
    with c1:
        threshold = st.slider("Defaulter if below (%)", 30, 90, ATTENDANCE_TARGET, key=f"{key}_th")
    with c2:
        secs = ["All"] + sorted(students["section"].dropna().unique().tolist())
        sec = st.selectbox("Section", secs, key=f"{key}_sec")
    with c3:
        search = st.text_input("Search name / roll", key=f"{key}_q")

    f1, f2 = st.columns(2)
    courses = ["All"] + sorted(students["course"].dropna().astype(str).unique().tolist())
    years = ["All"] + sorted(students["year"].dropna().astype(str).unique().tolist())
    course_pick = f1.selectbox("Course", courses, key=f"{key}_course")
    year_pick = f2.selectbox("Year", years, key=f"{key}_year")
    if course_pick != "All":
        students = students[students["course"].astype(str) == course_pick]
    if year_pick != "All":
        students = students[students["year"].astype(str) == year_pick]
    summ = student_attendance_summary(students, logs)
    summ = summ[(summ["total"] > 0) & (summ["pct"] < threshold)]
    if sec != "All":
        summ = summ[summ["section"] == sec]
    if search:
        s = search.lower()
        summ = summ[summ["name"].fillna("").str.lower().str.contains(s)
                    | summ["roll_no"].fillna("").astype(str).str.lower().str.contains(s)]
    summ = summ.sort_values("pct")

    st.metric("Defaulters", len(summ))
    if summ.empty:
        st.success("No defaulters 🎉")
        return

    table = summ[["name", "roll_no", "section", "parent_name", "parent_email", "present", "total", "pct"]].copy()
    table.insert(0, "Select", False)

    def _has_email(v):
        return bool(v) and "@" in str(v)

    usable = [bool(_has_email(v)) for v in table["parent_email"]]
    st.caption(f"{sum(usable)} of {len(table)} have a parent email address.")
    b1, b2, b3 = st.columns(3)
    if b1.button("Select all shown", key=f"{key}_all"):
        st.session_state[f"{key}_pick"] = [True] * len(table)
    if b2.button("Select all with a parent email", key=f"{key}_all_email"):
        st.session_state[f"{key}_pick"] = usable
    if b3.button("Clear selection", key=f"{key}_none"):
        st.session_state[f"{key}_pick"] = [False] * len(table)
    if f"{key}_pick" in st.session_state and len(st.session_state[f"{key}_pick"]) == len(table):
        table["Select"] = st.session_state[f"{key}_pick"]

    edited = st.data_editor(
        table, hide_index=True, width="stretch", key=f"{key}_editor",
        disabled=[c for c in table.columns if c != "Select"],
        column_config={"Select": st.column_config.CheckboxColumn("Select"),
                       "pct": st.column_config.NumberColumn("Attendance %", format="%.1f")})
    st.session_state[f"{key}_pick"] = [bool(v) for v in edited["Select"]]
    chosen = summ.loc[edited.index[edited["Select"]]]
    no_email = sum(1 for v in chosen["parent_email"] if not _has_email(v))
    if no_email:
        st.warning(f"{no_email} selected student(s) have no parent email and will be skipped.")
    if len(chosen) > 200:
        st.warning("Only the first 200 selected students are sent per click.")
        chosen = chosen.head(200)

    def _send(row):
        email = row.get("parent_email")
        if not email or "@" not in str(email):
            return False, "no parent email"
        sr, sess, mr, monthly = _build_report(row["student_id"], logs, subjects, marks)
        try:
            send_defaulter_report(
                email, row.get("parent_name"),
                {k: row.get(k) for k in ("name", "roll_no", "section", "course", "year")},
                row["pct"], sr, sess, mr, monthly)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _send_grouped(rows):
        """One email per parent address. A parent with one child gets the single-student email;
        a parent with several children gets one family email covering all of them."""
        groups = {}
        skipped = 0
        for _, r in rows.iterrows():
            email = r.get("parent_email")
            if not email or "@" not in str(email):
                skipped += 1
                continue
            groups.setdefault(str(email).strip().lower(), []).append(r)
        sent_emails = failed_emails = 0
        bar = st.progress(0.0)
        for i, (email, members) in enumerate(groups.items(), 1):
            try:
                if len(members) == 1:
                    ok, err = _send(members[0])
                    if not ok:
                        raise RuntimeError(err)
                else:
                    children = []
                    for r in members:
                        sr, sess, mr, monthly = _build_report(r["student_id"], logs, subjects, marks)
                        children.append({
                            "student": {k: r.get(k) for k in ("name", "roll_no", "section", "course", "year")},
                            "overall_pct": r["pct"], "subject_rows": sr, "session_rows": sess,
                            "marks_rows": mr, "monthly": monthly})
                    send_defaulter_family_report(email, members[0].get("parent_name"), children)
                sent_emails += 1
            except Exception as e:
                failed_emails += 1
                st.warning(f"{email}: {e}")
            bar.progress(i / len(groups))
        return sent_emails, failed_emails, skipped

    st.divider()
    b1, b2 = st.columns(2)
    with b1:
        if st.button(f"📧 Email each parent (one email per family) · {len(chosen)} student(s)",
                     type="primary", disabled=chosen.empty, key=f"{key}_sel"):
            sent_n, failed_n, skipped_n = _send_grouped(chosen)
            st.success(f"Emails sent: {sent_n}, failed: {failed_n}, skipped (no address): {skipped_n}. "
                       "A parent with several children received one email.")
    with b2:
        pick = st.selectbox("Or send to one student", summ["name"].tolist(), key=f"{key}_one")
        if st.button("📧 Email this parent", key=f"{key}_onebtn"):
            row = summ[summ["name"] == pick].iloc[0]
            good, err = _send(row)
            st.success(f"Email sent to {row['parent_email']}") if good else st.error(err)
