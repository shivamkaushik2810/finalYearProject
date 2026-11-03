import altair as alt
import pandas as pd
import streamlit as st


def _build_session_df(logs):
    if not logs:
        return pd.DataFrame(columns=["ts", "Attendance %"])
    df = pd.DataFrame(logs)
    df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["is_present"] = df["is_present"].fillna(False).astype(bool)
    df = df.dropna(subset=["ts"])
    return (
        df.groupby("ts")["is_present"]
        .mean().mul(100).round(1)
        .reset_index(name="Attendance %")
        .sort_values("ts")
    )


def _build_student_df(logs, enrolled):
    names = {s["student_id"]: s.get("name", "Unknown") for s in enrolled}
    if not logs:
        return pd.DataFrame(columns=["student_id", "name", "pct"])
    df = pd.DataFrame(logs)
    df["is_present"] = df["is_present"].fillna(False).astype(bool)
    out = (
        df.groupby("student_id")["is_present"]
        .mean().mul(100).round(1)
        .reset_index(name="pct")
    )
    out["name"] = out["student_id"].map(names).fillna("Unknown")
    return out


def _band(pct):
    if pct < 50:
        return "Below 50%"
    if pct < 75:
        return "50-75%"
    return "75% and above"


def show_attendance_analytics(logs, enrolled):
    st.subheader("Attendance Analytics")

    sessions = _build_session_df(logs)
    students = _build_student_df(logs, enrolled)

    if sessions.empty:
        st.info("No attendance sessions yet. Take attendance to see analytics.")
        return

    at_risk = int((students["pct"] < 75).sum()) if not students.empty else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Sessions", len(sessions))
    c2.metric("Average Attendance", f"{sessions['Attendance %'].mean():.1f}%")
    c3.metric("Students Below 75%", at_risk)

    st.markdown("#### Attendance trend by session")
    trend = (
        alt.Chart(sessions)
        .mark_line(point=True)
        .encode(
            x=alt.X("ts:T", title="Session date",
                    axis=alt.Axis(format="%d %b %H:%M")),
            y=alt.Y("Attendance %:Q", title="Attendance %",
                    scale=alt.Scale(domain=[0, 100], clamp=True)),
            tooltip=[
                alt.Tooltip("ts:T", title="Session", format="%d %b %Y %H:%M"),
                alt.Tooltip("Attendance %:Q"),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(trend, width='stretch')

    st.markdown("#### Students by attendance band")
    if students.empty:
        st.info("No per-student data yet.")
        return

    students["Band"] = students["pct"].apply(_band)
    order = ["Below 50%", "50-75%", "75% and above"]
    band_counts = (
        students.groupby("Band").size()
        .reindex(order, fill_value=0)
        .reset_index(name="Students")
    )
    bands = (
        alt.Chart(band_counts)
        .mark_bar()
        .encode(
            x=alt.X("Band:N", sort=order, title=None),
            y=alt.Y("Students:Q", title="Students",
                    axis=alt.Axis(tickMinStep=1, format="d")),
            tooltip=["Band", "Students"],
        )
        .properties(height=250)
    )
    st.altair_chart(bands, width='stretch')
