import altair as alt
import pandas as pd
import streamlit as st
from src.database.analytics_queries import load_core_frames, student_attendance_summary


def show_section_analytics():
    st.header("📊 Section-wise Analytics & Comparison")
    students, subjects, _, logs, marks = load_core_frames()
    if students.empty or logs.empty:
        st.info("Not enough data yet.")
        return

    f1, f2 = st.columns(2)
    with f1:
        courses = ["All"] + sorted(students["course"].dropna().unique().tolist())
        course = st.selectbox("Course", courses, key="secan_course")
    with f2:
        years = ["All"] + sorted(students["year"].dropna().astype(str).unique().tolist())
        year = st.selectbox("Year", years, key="secan_year")
    if course != "All":
        students = students[students["course"] == course]
    if year != "All":
        students = students[students["year"].astype(str) == year]

    # Label = only the parts that are still "All", so groups never get merged
    students = students.copy()
    _parts = []
    if course == "All":
        _parts.append(students["course"].fillna("N/A").astype(str))
    if year == "All":
        _parts.append("Y" + students["year"].fillna("?").astype(str))
    _parts.append(students["section"].fillna("N/A").astype(str))
    _label = _parts[0]
    for _p in _parts[1:]:
        _label = _label + " · " + _p
    students["section"] = _label

    logs = logs[logs["student_id"].isin(students["student_id"])]
    summ = student_attendance_summary(students, logs)
    summ["section"] = summ["section"].fillna("N/A")

    sec = (summ[summ["total"] > 0].groupby("section")
           .agg(students=("student_id", "count"), avg_pct=("pct", "mean"),
                defaulters=("pct", lambda s: int((s < 75).sum())),
                present=("present", "sum"), total=("total", "sum"))
           .reset_index())
    if sec.empty:
        st.info("No attendance in this selection.")
        return
    sec["avg_pct"] = sec["avg_pct"].round(1)
    sec["defaulter_pct"] = (sec["defaulters"] / sec["students"] * 100).round(1)

    k = st.columns(4)
    k[0].metric("Sections", len(sec))
    k[1].metric("Best section", sec.sort_values("avg_pct").iloc[-1]["section"])
    k[2].metric("Weakest section", sec.sort_values("avg_pct").iloc[0]["section"])
    k[3].metric("Total defaulters", int(sec["defaulters"].sum()))
    st.dataframe(sec.sort_values("avg_pct", ascending=False), hide_index=True, width="stretch")

    t1, t2, t3, t4, t5, t6 = st.tabs(
        ["Bar", "Pie / Donut", "Line trend", "Box plot", "Heatmap", "Scatter"])

    with t1:
        base = alt.Chart(sec).encode(x=alt.X("section:N", title="Section"))
        bars = base.mark_bar().encode(y=alt.Y("avg_pct:Q", title="Avg attendance %"),
                                      color="section:N", tooltip=list(sec.columns))
        rule = alt.Chart(pd.DataFrame({"y": [75]})).mark_rule(
            color="red", strokeDash=[5, 5]).encode(y="y:Q")
        st.altair_chart(bars + rule, width="stretch")
        d = sec.melt("section", ["students", "defaulters"], "type", "count")
        st.altair_chart(alt.Chart(d).mark_bar().encode(
            x="section:N", y="count:Q", color="type:N", xOffset="type:N"),
            width="stretch")

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Students per section")
            st.altair_chart(alt.Chart(sec).mark_arc(innerRadius=50).encode(
                theta="students:Q", color="section:N", tooltip=["section", "students"]),
                width="stretch")
        with c2:
            st.caption("Defaulters per section")
            st.altair_chart(alt.Chart(sec).mark_arc().encode(
                theta="defaulters:Q", color="section:N", tooltip=["section", "defaulters"]),
                width="stretch")

    with t3:
        m = logs.dropna(subset=["timestamp"]).merge(
            students[["student_id", "section"]], on="student_id")
        m["month"] = m["timestamp"].dt.strftime("%Y-%m")
        tr = (m.groupby(["month", "section"])["is_present"].mean() * 100).round(1).reset_index()
        tr.columns = ["month", "section", "pct"]
        st.altair_chart(alt.Chart(tr).mark_line(point=True).encode(
            x="month:N", y=alt.Y("pct:Q", title="Attendance %"),
            color="section:N", tooltip=["month", "section", "pct"]), width="stretch")

    with t4:
        st.altair_chart(alt.Chart(summ[summ["total"] > 0]).mark_boxplot().encode(
            x="section:N", y=alt.Y("pct:Q", title="Attendance %"), color="section:N"),
            width="stretch")

    with t5:
        if sub_ok := (not subjects.empty):
            sm = logs.merge(students[["student_id", "section"]], on="student_id") \
                     .merge(subjects[["subject_id", "name"]], on="subject_id")
            hm = (sm.groupby(["section", "name"])["is_present"].mean() * 100).round(1).reset_index()
            hm.columns = ["section", "subject", "pct"]
            base = alt.Chart(hm).encode(x="section:N", y="subject:N")
            st.altair_chart(
                base.mark_rect().encode(color=alt.Color("pct:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[0, 100])))
                + base.mark_text().encode(text="pct:Q"), width="stretch")

    with t6:
        if not marks.empty:
            mk = marks.merge(students[["student_id", "section"]], on="student_id") \
                      .groupby("student_id")["pct"].mean().reset_index(name="marks_pct")
            sc = summ.merge(mk, on="student_id")
            st.caption("Attendance vs marks per student — each dot is a student")
            st.altair_chart(alt.Chart(sc).mark_circle(size=50, opacity=0.6).encode(
                x=alt.X("pct:Q", title="Attendance %"), y=alt.Y("marks_pct:Q", title="Marks %"),
                color="section:N", tooltip=["name", "section", "pct", "marks_pct"]),
                width="stretch")
            ms = sc.groupby("section")["marks_pct"].mean().round(1).reset_index()
            st.altair_chart(alt.Chart(ms).mark_bar().encode(
                x="section:N", y=alt.Y("marks_pct:Q", title="Avg marks %"), color="section:N"),
                width="stretch")
        else:
            st.info("No marks uploaded yet.")

    st.download_button("⬇️ Download section summary (CSV)",
                       sec.to_csv(index=False).encode(), "section_summary.csv", "text/csv")
