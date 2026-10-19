import altair as alt
import numpy as np
import pandas as pd

CHART_TYPES = ["Bar", "Grouped bar", "Line", "Pie", "Donut", "Radar", "Scatter",
               "Stacked bar", "Area", "Histogram", "Box plot", "Heatmap"]
FIXED_WIDTH = {"Radar", "Grouped bar"}      # not stretched, to avoid distortion

BLUE, PINK, RED, GREEN, AMBER = "#5865F2", "#EB459E", "#e74c3c", "#28a745", "#f39c12"


def _bar(m, cfg):
    d = m["att_by_subject"]
    if d.empty:
        return None, "No attendance records for the selected filters."
    d = d[["subject", "present", "classes", "pct"]].copy()
    d["status"] = np.where(d["pct"] < cfg.attendance_target, "Below target", "On target")
    bars = alt.Chart(d).mark_bar().encode(
        x=alt.X("pct:Q", title="Attendance (%)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("subject:N", title="Subject", sort="-x"),
        color=alt.Color("status:N", title=None, scale=alt.Scale(domain=["On target", "Below target"], range=[BLUE, RED])),
        tooltip=[alt.Tooltip("subject:N", title="Subject"), alt.Tooltip("present:Q", title="Present"),
                 alt.Tooltip("classes:Q", title="Classes held"), alt.Tooltip("pct:Q", title="Attendance %", format=".1f")])
    rule = (alt.Chart(pd.DataFrame({"target": [cfg.attendance_target]}))
            .mark_rule(color=AMBER, strokeDash=[6, 4]).encode(x="target:Q"))
    return (bars + rule).properties(height=max(140, 42 * len(d))), None


def _grouped(m, cfg):
    a, k = m["att_by_subject"], m["marks_by_subject"]
    if a.empty or k.empty:
        return None, "Grouped bars need both attendance and marks."
    d = a[["subject_id", "subject", "pct"]].merge(k[["subject_id", "marks_pct"]], on="subject_id")
    if d.empty:
        return None, "No subject has both attendance and marks."
    long = pd.concat([d[["subject", "pct"]].rename(columns={"pct": "value"}).assign(metric="Attendance %"),
                      d[["subject", "marks_pct"]].rename(columns={"marks_pct": "value"}).assign(metric="Marks %")])
    chart = alt.Chart(long).mark_bar().encode(
        x=alt.X("metric:N", title=None, axis=alt.Axis(labels=False)),
        y=alt.Y("value:Q", title="Percent", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("metric:N", title=None, scale=alt.Scale(domain=["Attendance %", "Marks %"], range=[BLUE, PINK])),
        column=alt.Column("subject:N", title=None),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("metric:N"), alt.Tooltip("value:Q", format=".1f")]
    ).properties(width=70, height=220)
    return chart, None


def _line(m, cfg):
    w = m["weekly"]
    if len(w) < 3:
        return None, f"A time series needs at least 3 weeks with classes ({len(w)} available)."
    long = pd.concat([
        w[["week", "pct"]].rename(columns={"pct": "value"}).assign(series="Weekly attendance %"),
        w.dropna(subset=["ma"])[["week", "ma"]].rename(columns={"ma": "value"}).assign(series=f"{cfg.ma_window}-week moving average")])
    long["value"] = long["value"].astype(float)
    line = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("week:T", title="Week starting"),
        y=alt.Y("value:Q", title="Attendance (%)", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("series:N", title=None, scale=alt.Scale(range=[BLUE, PINK])),
        tooltip=[alt.Tooltip("week:T", title="Week of"), alt.Tooltip("series:N", title="Series"),
                 alt.Tooltip("value:Q", title="Attendance %", format=".1f")])
    rule = (alt.Chart(pd.DataFrame({"t": [cfg.attendance_target]}))
            .mark_rule(color=AMBER, strokeDash=[6, 4]).encode(y="t:Q"))
    return line + rule, None


def _pie(m, cfg):
    a = m["att"]
    if a["classes"] == 0:
        return None, "No attendance records for the selected filters."
    d = pd.DataFrame({"status": ["Present", "Absent"], "classes": [a["present"], a["absent"]]})
    chart = alt.Chart(d).mark_arc().encode(
        theta=alt.Theta("classes:Q"),
        color=alt.Color("status:N", title=None, scale=alt.Scale(domain=["Present", "Absent"], range=[GREEN, RED])),
        tooltip=[alt.Tooltip("status:N"), alt.Tooltip("classes:Q", title="Classes")])
    return chart.properties(height=260), None


def _donut(m, cfg):
    d = m["att_by_subject"]
    if len(d) < 2 or d["present"].sum() == 0:
        return None, "A share-of-classes donut needs attended classes in at least 2 subjects."
    d = d[["subject", "present"]]
    chart = alt.Chart(d).mark_arc(innerRadius=60).encode(
        theta=alt.Theta("present:Q"), color=alt.Color("subject:N", title="Subject"),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("present:Q", title="Classes attended")])
    return chart.properties(height=260), None


def _radar(m, cfg):
    a, k = m["att_by_subject"][["subject_id", "subject", "pct"]], m["marks_by_subject"][["subject_id", "marks_pct"]]
    d = a.merge(k, on="subject_id").dropna(subset=["pct", "marks_pct"]).reset_index(drop=True)
    n = len(d)
    if n < 3:
        return None, "A radar chart needs at least 3 subjects with both attendance and marks."
    ang = np.pi / 2 - np.arange(n) * 2 * np.pi / n
    X = alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-150, 150]))
    Y = alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-150, 150]))
    ring = [{"ring": r, "x": r * np.cos(t), "y": r * np.sin(t), "o": j}
            for r in (25, 50, 75, 100) for j, t in enumerate(np.linspace(0, 2 * np.pi, 73))]
    spokes = []
    for i, t in enumerate(ang):
        spokes += [{"spoke": i, "x": 0.0, "y": 0.0, "o": 0}, {"spoke": i, "x": 100 * np.cos(t), "y": 100 * np.sin(t), "o": 1}]
    labels = [{"x": 120 * np.cos(t), "y": 120 * np.sin(t), "label": s} for t, s in zip(ang, d["subject"])]
    poly = []
    for series, col in (("Attendance %", "pct"), ("Marks %", "marks_pct")):
        for j in range(n + 1):                       # repeat the first point to close the polygon
            i = j % n
            v = float(d[col].iloc[i])
            poly.append({"series": series, "subject": d["subject"].iloc[i], "value": round(v, 1),
                         "x": v * np.cos(ang[i]), "y": v * np.sin(ang[i]), "o": j})
    pdf = pd.DataFrame(poly)
    color = alt.Color("series:N", title=None, scale=alt.Scale(domain=["Attendance %", "Marks %"], range=[BLUE, PINK]))
    layers = [
        alt.Chart(pd.DataFrame(ring)).mark_line(color="#b0b3c7", opacity=0.5).encode(x=X, y=Y, detail="ring:N", order="o:Q"),
        alt.Chart(pd.DataFrame(spokes)).mark_line(color="#b0b3c7", opacity=0.5).encode(x=X, y=Y, detail="spoke:N", order="o:Q"),
        alt.Chart(pdf).mark_line(strokeWidth=2).encode(x=X, y=Y, color=color, detail="series:N", order="o:Q"),
        alt.Chart(pdf).mark_point(filled=True, size=70).encode(
            x=X, y=Y, color=color,
            tooltip=[alt.Tooltip("series:N"), alt.Tooltip("subject:N"), alt.Tooltip("value:Q", title="Percent")]),
        alt.Chart(pd.DataFrame(labels)).mark_text(fontSize=11).encode(x=X, y=Y, text="label:N"),
    ]
    return alt.layer(*layers).properties(width=380, height=380).configure_view(strokeWidth=0), None


def _scatter(m, cfg):
    p = m["pairs"]
    if len(p) < 3:
        return None, (f"A scatter plot needs at least 3 subjects with attendance (>= {cfg.min_subject_classes} classes) "
                      f"and marks ({len(p)} available).")
    base = alt.Chart(p[["subject", "pct", "marks_pct", "classes"]]).mark_circle(size=150, color=BLUE).encode(
        x=alt.X("pct:Q", title="Attendance (%)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("marks_pct:Q", title="Marks (%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("pct:Q", title="Attendance %", format=".1f"),
                 alt.Tooltip("marks_pct:Q", title="Marks %", format=".1f"), alt.Tooltip("classes:Q", title="Classes")])
    if m["corr"]["status"] == "ok":
        reg = (alt.Chart(p[["pct", "marks_pct"]]).transform_regression("pct", "marks_pct")
               .mark_line(color=AMBER).encode(x="pct:Q", y="marks_pct:Q"))
        return base + reg, "Each point is one subject. The line is a fitted trend; association is not causation."
    return base, "Each point is one subject. Too few subjects for a correlation or trend line."


def _stacked(m, cfg):
    d = m["att_by_subject"]
    if d.empty:
        return None, "No attendance records for the selected filters."
    long = pd.DataFrame({"subject": list(d["subject"]) * 2,
                         "status": ["Present"] * len(d) + ["Absent"] * len(d),
                         "classes": list(d["present"]) + list(d["absent"])})
    chart = alt.Chart(long).mark_bar().encode(
        x=alt.X("subject:N", title="Subject"), y=alt.Y("classes:Q", title="Classes held"),
        color=alt.Color("status:N", title=None, scale=alt.Scale(domain=["Present", "Absent"], range=[GREEN, RED])),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("status:N"), alt.Tooltip("classes:Q")])
    return chart, None


def _area(m, cfg):
    d = m["att_df"]
    if d.empty:
        return None, "No attendance records for the selected filters."
    daily = d.groupby("date", as_index=False).agg(classes=("present", "size"), present=("present", "sum")).sort_values("date")
    if len(daily) < 4:
        return None, f"A time series needs at least 4 class days ({len(daily)} available)."
    daily["cum_pct"] = daily["present"].cumsum() / daily["classes"].cumsum() * 100
    chart = alt.Chart(daily[["date", "cum_pct"]]).mark_area(opacity=0.35, line=True, color=BLUE).encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("cum_pct:Q", title="Cumulative attendance (%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("cum_pct:Q", title="Cumulative %", format=".1f")])
    return chart, None


def _hist(m, cfg):
    d = m["marks_df"]
    if len(d) < cfg.min_hist_points:
        return None, f"A histogram needs at least {cfg.min_hist_points} scored assessments ({len(d)} available)."
    chart = alt.Chart(d[["pct"]]).mark_bar(color=BLUE).encode(
        x=alt.X("pct:Q", bin=alt.Bin(extent=[0, 100], step=10), title="Assessment score (%)"),
        y=alt.Y("count():Q", title="Assessments"))
    return chart, None


def _box(m, cfg):
    d = m["att_df"]
    if d.empty:
        return None, "No attendance records for the selected filters."
    w = d.copy()
    w["week"] = w["when"].dt.to_period("W-SUN").dt.start_time
    g = w.groupby(["subject", "week"], as_index=False).agg(classes=("present", "size"), present=("present", "sum"))
    g["pct"] = g["present"] / g["classes"] * 100
    g = g[g.groupby("subject")["pct"].transform("size") >= cfg.min_box_points]
    if g.empty:
        return None, f"A box plot needs at least {cfg.min_box_points} weeks of attendance in a subject."
    chart = alt.Chart(g[["subject", "pct"]]).mark_boxplot(extent=1.5, color=BLUE).encode(
        x=alt.X("pct:Q", title="Weekly attendance (%)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("subject:N", title="Subject"))
    return chart, "Each observation is one week's attendance % in that subject."


def _heatmap(m, cfg):
    d = m["att_df"]
    if d.empty:
        return None, "No attendance records for the selected filters."
    w = d.copy()
    w["month"] = w["when"].dt.to_period("M").dt.start_time
    g = w.groupby(["subject", "month"], as_index=False).agg(classes=("present", "size"), present=("present", "sum"))
    g["pct"] = (g["present"] / g["classes"] * 100).round(1)
    if len(g) < 2:
        return None, "A heatmap needs at least 2 subject-month cells."
    g["month_label"] = g["month"].dt.strftime("%b %Y")
    order = list(g.sort_values("month")["month_label"].drop_duplicates())
    g = g[["subject", "month_label", "classes", "pct"]]
    x, y = alt.X("month_label:O", sort=order, title="Month"), alt.Y("subject:N", title="Subject")
    rect = alt.Chart(g).mark_rect().encode(
        x=x, y=y, color=alt.Color("pct:Q", title="Attendance %", scale=alt.Scale(domain=[0, 100], scheme="redyellowgreen")),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("month_label:O", title="Month"),
                 alt.Tooltip("pct:Q", title="Attendance %"), alt.Tooltip("classes:Q", title="Classes")])
    text = alt.Chart(g).mark_text(fontSize=11).encode(x=x, y=y, text=alt.Text("pct:Q", format=".0f"))
    return rect + text, None


_BUILDERS = {
    "Bar": (_bar, "Attendance by subject (red = below target)"),
    "Grouped bar": (_grouped, "Attendance % vs marks % by subject"),
    "Line": (_line, "Weekly attendance trend"),
    "Pie": (_pie, "Present vs absent classes"),
    "Donut": (_donut, "Share of attended classes by subject"),
    "Radar": (_radar, "Subject profile: attendance vs marks"),
    "Scatter": (_scatter, "Attendance vs marks (one point per subject)"),
    "Stacked bar": (_stacked, "Present and absent classes by subject"),
    "Area": (_area, "Cumulative attendance over time"),
    "Histogram": (_hist, "Distribution of assessment scores"),
    "Box plot": (_box, "Weekly attendance spread by subject"),
    "Heatmap": (_heatmap, "Attendance % by subject and month"),
}


def build_chart(kind, m, cfg):
    fn, title = _BUILDERS[kind]
    chart, note = fn(m, cfg)
    return {"title": title, "chart": chart, "note": note}


def forecast_chart(m):
    f, w = m["forecast"], m["weekly"]
    if f.get("status") != "ok":
        return None
    fut = pd.DataFrame(f["forecast"])
    hist = w[["week", "pct"]]
    line = alt.Chart(hist).mark_line(point=True, color=BLUE).encode(
        x=alt.X("week:T", title="Week starting"),
        y=alt.Y("pct:Q", title="Attendance (%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("week:T"), alt.Tooltip("pct:Q", title="Observed %", format=".1f")])
    band = alt.Chart(fut).mark_area(opacity=0.2, color=AMBER).encode(x="week:T", y="low:Q", y2="high:Q")
    pred = alt.Chart(fut).mark_line(point=True, color=AMBER, strokeDash=[5, 3]).encode(
        x="week:T", y="pred:Q",
        tooltip=[alt.Tooltip("week:T"), alt.Tooltip("pred:Q", title="Forecast %", format=".1f"),
                 alt.Tooltip("low:Q", title="Low", format=".1f"), alt.Tooltip("high:Q", title="High", format=".1f")])
    return alt.layer(band, line, pred)


def marks_progress_chart(m, cfg):
    d = m["marks_df"].dropna(subset=["when"])
    if d.empty:
        return None
    d = d[["when", "pct", "subject", "exam_type"]]
    line = alt.Chart(d).mark_line(point=True).encode(
        x=alt.X("when:T", title="Assessment date"),
        y=alt.Y("pct:Q", title="Score (%)", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("subject:N", title="Subject"),
        tooltip=[alt.Tooltip("subject:N"), alt.Tooltip("exam_type:N", title="Exam"),
                 alt.Tooltip("pct:Q", title="Score %", format=".1f"), alt.Tooltip("when:T", title="Date")])
    rule = (alt.Chart(pd.DataFrame({"t": [cfg.marks_target]})).mark_rule(color=AMBER, strokeDash=[6, 4]).encode(y="t:Q"))
    return line + rule


def chart_png(chart, scale=2):
    """PNG bytes of an Altair chart, or None if image export is unavailable (needs vl-convert-python)."""
    try:
        import io
        buf = io.BytesIO()
        chart.save(buf, format="png", scale_factor=scale)
        return buf.getvalue()
    except Exception as e:
        print(f"Chart image export unavailable: {type(e).__name__}")
        return None
