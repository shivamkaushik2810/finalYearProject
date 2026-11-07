from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.ui.widgets import esc


def _truthy(v):
    return v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1)


def logs_to_df(logs):
    """attendance_logs rows -> DataFrame[date, present]. Bad timestamps are dropped."""
    empty = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "present": pd.Series(dtype="bool")})
    if not logs:
        return empty
    df = pd.DataFrame(logs)
    if "timestamp" not in df:
        return empty
    ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="ISO8601").dt.tz_convert(None)
    present = df["is_present"].map(_truthy) if "is_present" in df else pd.Series(False, index=df.index)
    out = pd.DataFrame({"date": ts, "present": present.astype(bool)})
    return out.dropna(subset=["date"]).reset_index(drop=True)


def weekly_trend(df):
    if df.empty:
        return pd.DataFrame({"Attendance %": []})
    week = df["date"].dt.to_period("W").dt.start_time
    series = df.groupby(week)["present"].mean() * 100
    return pd.DataFrame({"Attendance %": series.round(1)})


def heatmap_rows(df, weeks=4, today=None):
    """Return [(week_label, [(symbol, kind, tooltip) x 6])] for Monday to Saturday."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    daily = {}
    for d, p in zip(df["date"].dt.date, df["present"]):
        cell = daily.setdefault(d, [0, 0])
        cell[1] += 1
        cell[0] += int(p)
    rows = []
    for w in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=w)
        cells = []
        for i in range(6):
            d = start + timedelta(days=i)
            if d > today or d not in daily:
                cells.append(("\u00b7", "none", f"{d:%d %b}: no class"))
                continue
            p, t = daily[d]
            if p == t:
                cells.append(("\u2713", "good", f"{d:%d %b}: present {p} of {t}"))
            elif p == 0:
                cells.append(("\u2717", "risk", f"{d:%d %b}: absent {t} of {t}"))
            else:
                cells.append(("~", "avg", f"{d:%d %b}: present {p} of {t}"))
        rows.append((f"{start:%d %b}", cells))
    return rows


def attendance_trend(logs, title="Attendance trend by week"):
    st.markdown(f"**{esc(title)}**")
    tr = weekly_trend(logs_to_df(logs))
    if tr.empty:
        st.caption("The chart appears after the first attendance session.")
        return
    st.line_chart(tr, height=220)


def subject_bars(rows, title="Attendance by subject"):
    """rows: list of (subject_name, percent)."""
    st.markdown(f"**{esc(title)}**")
    if not rows:
        st.caption("No subjects to compare yet.")
        return
    df = pd.DataFrame(rows, columns=["Subject", "Attendance %"]).set_index("Subject")
    st.bar_chart(df, height=220)


def weekly_heatmap(logs, weeks=4, title="Last weeks at a glance"):
    st.markdown(f"**{esc(title)}**")
    df = logs_to_df(logs)
    if df.empty:
        st.caption("No sessions recorded yet.")
        return
    head = "".join(f"<span class='c'>{d}</span>" for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"))
    html_rows = [f"<span></span>{head}"]
    style = {"good": "background:#EAF3DE;color:#3B6D11", "avg": "background:#FAEEDA;color:#854F0B",
             "risk": "background:#FCEBEB;color:#A32D2D", "none": "background:#e2e8f0;color:#475569"}
    for label, cells in heatmap_rows(df, weeks):
        html_rows.append(f"<span>{esc(label)}</span>")
        for sym, kind, tip in cells:
            html_rows.append(f"<span class='c' style='{style[kind]}' title='{esc(tip)}'>{sym}</span>")
    st.markdown(f"<div class='sc-hm'>{''.join(html_rows)}</div>", unsafe_allow_html=True)
    st.caption("\u2713 all present, ~ some present, \u2717 all absent, \u00b7 no class")
