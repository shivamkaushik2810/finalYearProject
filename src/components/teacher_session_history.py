import altair as alt
import pandas as pd
import streamlit as st
from src.database.analytics_queries import load_core_frames


def show_teacher_session_history():
    if not st.session_state.get("admin_data"):
        st.error("Admin login required.")
        return
    st.header("🧑‍🏫 Teacher Session History")
    students, subjects, teachers, logs, _ = load_core_frames()
    if logs.empty or subjects.empty:
        st.info("No sessions recorded yet.")
        return

    # one session = one (subject, timestamp)
    sess = (logs.dropna(subset=["timestamp"]).groupby(["subject_id", "timestamp"])
            .agg(present=("is_present", "sum"), enrolled=("is_present", "count"))
            .reset_index())
    sess = sess.merge(subjects[["subject_id", "name", "subject_code", "section", "teacher_id"]],
                      on="subject_id", how="left")
    sess = sess.merge(teachers[["teacher_id", "name"]].rename(columns={"name": "teacher"}),
                      on="teacher_id", how="left")
    sess["teacher"] = sess["teacher"].fillna("Unknown")
    sess["section"] = sess["section"].fillna("N/A")
    sess["attendance_pct"] = (sess["present"] / sess["enrolled"] * 100).round(1)
    sess["date"] = sess["timestamp"].dt.date

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        tsel = st.selectbox("Teacher", ["All"] + sorted(sess["teacher"].unique()), key="tsess_t")
    with f2:
        ssel = st.selectbox("Section", ["All"] + sorted(sess["section"].unique()), key="tsess_s")
    with f3:
        d_from = st.date_input("From", sess["date"].min(), key="tsess_from")
    with f4:
        d_to = st.date_input("To", sess["date"].max(), key="tsess_to")

    v = sess.copy()
    if tsel != "All":
        v = v[v["teacher"] == tsel]
    if ssel != "All":
        v = v[v["section"] == ssel]
    v = v[(v["date"] >= d_from) & (v["date"] <= d_to)]
    if v.empty:
        st.warning("No sessions match these filters.")
        return

    k = st.columns(4)
    k[0].metric("Sessions", len(v))
    k[1].metric("Teachers", v["teacher"].nunique())
    k[2].metric("Sections covered", v["section"].nunique())
    k[3].metric("Avg attendance", f"{v['attendance_pct'].mean():.1f}%")

    tab_t, tab_m, tab_g = st.tabs(["📋 All sessions", "🧮 Teacher × Section", "📈 Graphs"])

    with tab_t:
        show = v.sort_values("timestamp", ascending=False)[
            ["timestamp", "teacher", "section", "name", "subject_code", "present", "enrolled", "attendance_pct"]]
        show.columns = ["Time", "Teacher", "Section", "Subject", "Code", "Present", "Enrolled", "Attendance %"]
        st.dataframe(show, hide_index=True, width="stretch")
        st.download_button("⬇️ Download (CSV)", show.to_csv(index=False).encode(),
                           "teacher_sessions.csv", "text/csv")

    with tab_m:
        pv = v.pivot_table(index="teacher", columns="section", values="subject_id",
                           aggfunc="count", fill_value=0)
        st.caption("Number of sessions each teacher took in each section")
        st.dataframe(pv, width="stretch")

    with tab_g:
        tc = v.groupby(["teacher", "section"]).size().reset_index(name="sessions")
        st.caption("Sessions by teacher, split by section")
        st.altair_chart(alt.Chart(tc).mark_bar().encode(
            x=alt.X("teacher:N", title="Teacher"), y="sessions:Q",
            color="section:N", tooltip=["teacher", "section", "sessions"]), width="stretch")

        hm = v.groupby(["teacher", "section"]).size().reset_index(name="sessions")
        base = alt.Chart(hm).encode(x="section:N", y="teacher:N")
        st.altair_chart(base.mark_rect().encode(color="sessions:Q")
                        + base.mark_text().encode(text="sessions:Q"), width="stretch")

        daily = v.groupby(["date", "teacher"]).size().reset_index(name="sessions")
        daily["date"] = pd.to_datetime(daily["date"])
        st.caption("Sessions over time")
        st.altair_chart(alt.Chart(daily).mark_line(point=True).encode(
            x="date:T", y="sessions:Q", color="teacher:N"), width="stretch")

        c1, c2 = st.columns(2)
        with c1:
            st.caption("Share of sessions per teacher")
            tt = v.groupby("teacher").size().reset_index(name="sessions")
            st.altair_chart(alt.Chart(tt).mark_arc(innerRadius=45).encode(
                theta="sessions:Q", color="teacher:N"), width="stretch")
        with c2:
            st.caption("Avg attendance per teacher")
            ta = v.groupby("teacher")["attendance_pct"].mean().round(1).reset_index()
            st.altair_chart(alt.Chart(ta).mark_bar().encode(
                x="teacher:N", y="attendance_pct:Q", color="teacher:N"), width="stretch")
