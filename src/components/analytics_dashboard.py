import altair as alt
import pandas as pd
import streamlit as st

BAND_ORDER = ["Below 50%", "50-75%", "75% and above"]
_COLS = ("student_id", "timestamp", "is_present")


def _parse_ts(series):
    """Parse DB timestamps; survives a mix of naive and tz-aware strings."""
    try:
        ts = pd.to_datetime(series, errors="coerce")
    except (ValueError, TypeError):
        ts = pd.to_datetime(series, errors="coerce", utc=True)
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(series, errors="coerce", utc=True)
    return ts


def _clean_logs(logs, enrolled=None):
    """
    Valid log rows only. When `enrolled` is given (even empty), logs of students who are
    not currently enrolled are dropped so they never appear as 'Unknown'.
    """
    if not logs:
        return pd.DataFrame(columns=list(_COLS))
    df = pd.DataFrame(logs)
    for col in _COLS:
        if col not in df.columns:
            df[col] = None
    df = df[df["student_id"].notna()].copy()
    if enrolled is not None:
        ids = {s.get("student_id") for s in enrolled if s.get("student_id")}
        df = df[df["student_id"].isin(ids)]
    df["is_present"] = df["is_present"].map(lambda v: bool(v) if pd.notna(v) else False)
    return df


def _overall_pct(logs, enrolled=None):
    """Total present / total records (same definition as the risk screens). None if no data."""
    df = _clean_logs(logs, enrolled)
    if df.empty:
        return None
    return round(float(df["is_present"].mean()) * 100, 1)


def _build_session_df(logs, enrolled=None):
    empty = pd.DataFrame(columns=["ts", "Attendance %"])
    df = _clean_logs(logs, enrolled)
    if df.empty:
        return empty
    df["ts"] = _parse_ts(df["timestamp"])
    df = df.dropna(subset=["ts"])
    if df.empty:
        return empty
    df["ts"] = df["ts"].dt.floor("s")   # one session = one second, ignore fractions
    return (
        df.groupby("ts")["is_present"]
        .mean().mul(100).round(1)
        .reset_index(name="Attendance %")
        .sort_values("ts")
    )


def _build_student_df(logs, enrolled):
    names = {s["student_id"]: s.get("name", "Unknown") for s in (enrolled or [])}
    df = _clean_logs(logs, enrolled if enrolled is not None else [])
    if df.empty:
        return pd.DataFrame(columns=["student_id", "name", "pct"])
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

    enrolled = enrolled or []
    if not enrolled:
        st.info("No students are enrolled in this subject yet.")
        return

    sessions = _build_session_df(logs, enrolled)
    students = _build_student_df(logs, enrolled)

    if sessions.empty:
        st.info("No attendance sessions yet. Take attendance to see analytics.")
        return

    overall = _overall_pct(logs, enrolled)
    at_risk = int((students["pct"] < 75).sum()) if not students.empty else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Sessions", len(sessions))
    c2.metric("Average Attendance", f"{overall:.1f}%" if overall is not None else "N/A")
    c3.metric("Students Below 75%", at_risk)

    no_records = len({s["student_id"] for s in enrolled} - set(students["student_id"]))
    if no_records:
        st.caption(f"{no_records} enrolled student(s) have no attendance records yet and are not counted below.")

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
    band_counts = (
        students.groupby("Band").size()
        .reindex(BAND_ORDER, fill_value=0)
        .reset_index(name="Students")
    )
    bands = (
        alt.Chart(band_counts)
        .mark_bar()
        .encode(
            x=alt.X("Band:N", sort=BAND_ORDER, title=None),
            y=alt.Y("Students:Q", title="Students",
                    axis=alt.Axis(tickMinStep=1, format="d")),
            tooltip=["Band", "Students"],
        )
        .properties(height=250)
    )
    st.altair_chart(bands, width='stretch')
