import numpy as np
import pandas as pd
import altair as alt
import streamlit as st

alt.data_transformers.disable_max_rows()

DEFAULT_THR = 75
MODES = ["Course · Year · Section", "Section only"]
METRICS = {"Average attendance %": "AvgPct", "Students": "Students", "Defaulters": "Defaulters",
           "Defaulter rate %": "DefRate", "Subjects": "Subjects"}
KINDS = ["Bar", "Horizontal bar", "Line", "Area", "Pie", "Donut", "Scatter (students vs attendance)"]
OK_LBL = "At/above threshold"
BELOW_LBL = "Below threshold"


# ───────────── shared helpers (also used by teacher_sessions) ─────────────

def _pct(num, den):
    n = pd.to_numeric(num, errors="coerce").fillna(0).astype(float)
    d = pd.to_numeric(den, errors="coerce").fillna(0).astype(float)
    safe = d.where(d > 0, 1.0)
    return pd.Series(np.where(d > 0, n / safe * 100, 0.0), index=n.index).round(1)


def _clean(series, fallback="—"):
    out = series.fillna("").astype(str).str.strip()
    return out.replace({"": fallback, "None": fallback, "nan": fallback})


def _page_all(table, select, order):
    from src.database.config import supabase
    out, start = [], 0
    while True:
        q = supabase.table(table).select(select)
        for c in order:
            q = q.order(c)
        rows = q.range(start, start + 999).execute().data or []
        out.extend(rows)
        if len(rows) < 1000:
            break
        start += 1000
    return out


def _show(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def _dl(df, title, subtitle, base, key):
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{base}.csv", mime="text/csv", key=f"{key}_csv")
    try:
        from src.services.report_export import df_pdf
        c2.download_button("⬇️ PDF", df_pdf(df, title, subtitle),
                           file_name=f"{base}.pdf", mime="application/pdf", key=f"{key}_pdf")
    except Exception as e:
        print(f"PDF export unavailable: {type(e).__name__}")


# ───────────── data (admin only, cached 5 min) ─────────────

@st.cache_data(ttl=300, show_spinner="Loading section data (cached for 5 minutes)...")
def _load():
    subjects = _page_all("subjects", "subject_id, name, subject_code, section, course, year, teachers(name)", ["subject_id"])
    pairs = _page_all("admin_pair_stats", "subject_id, student_id, total, present", ["subject_id", "student_id"])
    return subjects, pairs


@st.cache_data(ttl=300, show_spinner=False)
def _student_names():
    rows = _page_all("students", "student_id, name, roll_no", ["student_id"])
    d = pd.DataFrame(rows, columns=["student_id", "name", "roll_no"])
    d["student_id"] = d["student_id"].astype(str)
    return d.rename(columns={"name": "Name", "roll_no": "Roll No"})


# ───────────── pure logic (unit-tested) ─────────────

def build_frame(subjects, pairs):
    if not subjects or not pairs:
        return pd.DataFrame()
    sdf, pdf = pd.DataFrame(subjects), pd.DataFrame(pairs)
    if not {"subject_id", "name"} <= set(sdf.columns):
        return pd.DataFrame()
    if not {"subject_id", "student_id", "total", "present"} <= set(pdf.columns):
        return pd.DataFrame()
    for c in ("subject_code", "section", "course", "year", "teachers"):
        if c not in sdf.columns:
            sdf[c] = None
    sdf["subject_id"] = sdf["subject_id"].astype(str)
    pdf["subject_id"] = pdf["subject_id"].astype(str)
    sdf["teacher"] = sdf["teachers"].apply(
        lambda t: (t.get("name") if isinstance(t, dict) else None) or "Unknown")
    for c in ("section", "course", "year"):
        sdf[c] = _clean(sdf[c])
    sdf["name"] = _clean(sdf["name"], "Unnamed")
    sdf["subject_code"] = _clean(sdf["subject_code"], "")
    df = pdf.merge(sdf[["subject_id", "name", "subject_code", "section", "course", "year", "teacher"]],
                   on="subject_id", how="inner")
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df["present"] = pd.to_numeric(df["present"], errors="coerce").fillna(0)
    df["present"] = df[["present", "total"]].min(axis=1)
    return df


def add_group(df, mode):
    if df.empty:
        return df
    out = df.copy()
    if mode == "Section only":
        out["grp"] = "Section " + out["section"]
    else:
        out["grp"] = out["course"] + " · Y" + out["year"] + " · " + out["section"]
    return out


def section_summary(df, thr):
    """Returns (summary per section, per-student frame). Never produces NA percentages."""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    stu = df.groupby(["grp", "student_id"], as_index=False)[["total", "present"]].sum()
    stu = stu[stu["total"] > 0].copy()
    stu["pct"] = _pct(stu["present"], stu["total"])
    base = df.groupby("grp", as_index=False).agg(
        Subjects=("subject_id", "nunique"), Total=("total", "sum"), Present=("present", "sum"))
    if stu.empty:
        cnt = pd.DataFrame({"grp": base["grp"], "Students": 0, "Defaulters": 0})
    else:
        stu["below"] = stu["pct"] < thr
        cnt = stu.groupby("grp", as_index=False).agg(
            Students=("student_id", "nunique"), Defaulters=("below", "sum"))
    s = base.merge(cnt, on="grp", how="left")
    s["Students"] = s["Students"].fillna(0).astype(int)
    s["Defaulters"] = s["Defaulters"].fillna(0).astype(int)
    s["AvgPct"] = _pct(s["Present"], s["Total"])
    s["DefRate"] = _pct(s["Defaulters"], s["Students"])
    s = s.rename(columns={"grp": "Section"}).sort_values("AvgPct").reset_index(drop=True)
    return s, stu.rename(columns={"grp": "Section"})


def heatmap_frame(df):
    h = df.groupby(["grp", "name"], as_index=False).agg(Total=("total", "sum"), Present=("present", "sum"))
    h["AvgPct"] = _pct(h["Present"], h["Total"])
    return h.rename(columns={"grp": "Section", "name": "Subject"})


# ───────────── charts ─────────────

def compare_chart(summary, metric_col, metric_label, kind):
    if kind.startswith("Scatter"):
        d = summary[["Section", "Students", "AvgPct", "Defaulters"]]
        return alt.Chart(d).mark_circle(opacity=0.8).encode(
            x=alt.X("Students:Q"),
            y=alt.Y("AvgPct:Q", title="Average attendance %", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("Defaulters:Q", title="Defaulters"),
            color="Section:N",
            tooltip=["Section", "Students", "AvgPct", "Defaulters"]).properties(height=360)
    d = summary[["Section", metric_col]].rename(columns={metric_col: "Value"})
    tip = ["Section", alt.Tooltip("Value:Q", title=metric_label)]
    ch = alt.Chart(d)
    ycol = alt.Y("Value:Q", title=metric_label)
    if kind == "Bar":
        c = ch.mark_bar().encode(x=alt.X("Section:N", sort="-y"), y=ycol,
                                 color=alt.Color("Section:N", legend=None), tooltip=tip)
    elif kind == "Horizontal bar":
        c = ch.mark_bar().encode(y=alt.Y("Section:N", sort="-x"), x=alt.X("Value:Q", title=metric_label),
                                 color=alt.Color("Section:N", legend=None), tooltip=tip)
    elif kind == "Line":
        c = ch.mark_line(point=True).encode(x="Section:N", y=ycol, tooltip=tip)
    elif kind == "Area":
        c = ch.mark_area(opacity=0.5, line=True).encode(x="Section:N", y=ycol, tooltip=tip)
    elif kind == "Pie":
        c = ch.mark_arc().encode(theta="Value:Q", color="Section:N", tooltip=tip)
    else:
        c = ch.mark_arc(innerRadius=70).encode(theta="Value:Q", color="Section:N", tooltip=tip)
    return c.properties(height=360)


def box_chart(stu):
    return alt.Chart(stu).mark_boxplot(extent="min-max").encode(
        x="Section:N",
        y=alt.Y("pct:Q", title="Student attendance %", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Section:N", legend=None)).properties(height=360)


def hist_chart(stu):
    return alt.Chart(stu).mark_bar().encode(
        x=alt.X("pct:Q", bin=alt.Bin(step=10), title="Attendance % (10-point bins)"),
        y=alt.Y("count()", title="Students"),
        color="Section:N").properties(height=320)


def stacked_chart(summary):
    m = summary.assign(a=summary["Students"] - summary["Defaulters"])[["Section", "a", "Defaulters"]]
    m = m.rename(columns={"a": OK_LBL, "Defaulters": BELOW_LBL}).melt("Section", var_name="Status", value_name="Students")
    return alt.Chart(m).mark_bar().encode(
        x="Section:N", y="Students:Q",
        color=alt.Color("Status:N", scale=alt.Scale(domain=[OK_LBL, BELOW_LBL], range=["#28a745", "#e74c3c"])),
        tooltip=["Section", "Status", "Students"]).properties(height=340)


def heatmap_chart(h):
    base = alt.Chart(h).encode(x=alt.X("Subject:N", title=None), y=alt.Y("Section:N", title=None))
    rect = base.mark_rect().encode(
        color=alt.Color("AvgPct:Q", title="Avg %", scale=alt.Scale(domain=[0, 100], scheme="redyellowgreen")),
        tooltip=["Section", "Subject", "AvgPct"])
    text = base.mark_text(fontSize=10).encode(text=alt.Text("AvgPct:Q", format=".0f"))
    return (rect + text).properties(height=max(220, 30 * h["Section"].nunique()))


# ───────────── UI ─────────────

def section_analytics_tab():
    if not st.session_state.get("admin_data"):
        st.error("Admin login required.")
        return
    try:
        subjects, pairs = _load()
    except Exception as e:
        print(f"section_analytics load failed: {type(e).__name__}: {e}")
        st.error("Could not load attendance data. This tab needs the admin_pair_stats view "
                 "(also used by Overview & Reports).")
        return

    top = st.columns([5, 1])
    top[0].caption("Data is cached for 5 minutes. Press Refresh after new attendance is saved.")
    if top[1].button("Refresh", key="secan_refresh"):
        st.cache_data.clear()
        st.rerun()

    base = build_frame(subjects, pairs)
    if base.empty:
        st.info("No attendance data yet.")
        return

    f1, f2, f3, f4 = st.columns([1, 1, 1.8, 1.2])
    course = f1.selectbox("Course", ["All"] + sorted(base["course"].unique()), key="secan_course")
    year = f2.selectbox("Year", ["All"] + sorted(base["year"].unique()), key="secan_year")
    mode = f3.selectbox("Compare by", MODES, key="secan_mode")
    thr = f4.slider("Defaulter threshold %", 40, 95, DEFAULT_THR, 5, key="secan_thr")

    df = base
    if course != "All":
        df = df[df["course"] == course]
    if year != "All":
        df = df[df["year"] == year]
    df = add_group(df, mode)
    summary, stu = section_summary(df, thr)
    if summary.empty:
        st.info("No data for this selection.")
        return

    scored = summary[summary["Total"] > 0]
    k1, k2, k3, k4 = st.columns([1, 1, 2, 2])
    k1.metric("Sections", len(summary))
    k2.metric("Students", int(stu["student_id"].nunique()) if not stu.empty else 0)
    can_compare = len(scored) >= 2
    k3.caption("Best section")
    k3.markdown(f"**{scored.iloc[-1]['Section']}**" if can_compare else "—")
    k4.caption("Weakest section")
    k4.markdown(f"**{scored.iloc[0]['Section']}**" if can_compare else "—")
    if not can_compare:
        st.caption("Select more courses/years (or All) to compare at least two sections.")

    show = summary.rename(columns={"AvgPct": "Avg attendance %", "DefRate": "Defaulter rate %"})[
        ["Section", "Subjects", "Students", "Defaulters", "Defaulter rate %", "Avg attendance %"]]
    st.dataframe(show, hide_index=True, width="stretch")
    _dl(show, "Section Comparison", f"{course} | Year {year} | threshold {thr}%", "section_comparison", "secan_sum")

    t1, t2, t3, t4 = st.tabs(["Compare sections", "Distribution", "Heatmap", "Drill into a section"])

    with t1:
        c1, c2 = st.columns(2)
        label = c1.selectbox("Metric", list(METRICS.keys()), key="secan_metric")
        kind = c2.selectbox("Chart type", KINDS, key="secan_kind")
        if st.checkbox("Show every chart type at once", key="secan_all"):
            cols = st.columns(2)
            for i, k in enumerate(KINDS):
                with cols[i % 2]:
                    st.caption(k)
                    _show(compare_chart(summary, METRICS[label], label, k))
        else:
            _show(compare_chart(summary, METRICS[label], label, kind))
        st.caption("Defaulters vs students meeting the threshold")
        _show(stacked_chart(summary))

    with t2:
        if stu.empty:
            st.info("No student-level data.")
        else:
            st.caption("Box plot: spread of student attendance % in each section")
            _show(box_chart(stu))
            secs = list(summary["Section"])
            pick = st.multiselect("Sections for the histogram", secs, default=secs[:5], key="secan_hist")
            if pick:
                _show(hist_chart(stu[stu["Section"].isin(pick)]))

    with t3:
        h = heatmap_frame(df)
        if h["Subject"].nunique() > 40:
            st.warning("Many subjects selected; narrow Course/Year for a readable heatmap.")
        _show(heatmap_chart(h))

    with t4:
        sel = st.selectbox("Section", list(summary["Section"]), key="secan_sel")
        d = df[df["grp"] == sel]
        by = d.groupby(["name", "subject_code", "teacher"], as_index=False).agg(
            Students=("student_id", "nunique"), Total=("total", "sum"), Present=("present", "sum"))
        by["AvgPct"] = _pct(by["Present"], by["Total"])
        tbl = by.rename(columns={"name": "Subject", "subject_code": "Code", "teacher": "Teacher",
                                 "AvgPct": "Avg attendance %"})[
            ["Subject", "Code", "Teacher", "Students", "Avg attendance %"]]
        st.dataframe(tbl, hide_index=True, width="stretch")
        if not by.empty:
            _show(alt.Chart(by).mark_bar().encode(
                y=alt.Y("name:N", sort="-x", title=None),
                x=alt.X("AvgPct:Q", title="Avg attendance %", scale=alt.Scale(domain=[0, 100])),
                tooltip=["name", "teacher", "AvgPct"]).properties(height=max(160, 32 * len(by))))

        st.subheader(f"Students below {thr}% in {sel}")
        low = stu[(stu["Section"] == sel) & (stu["pct"] < thr)].sort_values("pct") if not stu.empty else stu
        if low.empty:
            st.success("No students below the threshold.")
        else:
            low = low.assign(student_id=low["student_id"].astype(str))
            try:
                low = low.merge(_student_names(), on="student_id", how="left")
            except Exception as e:
                print(f"student names unavailable: {type(e).__name__}")
                low["Name"], low["Roll No"] = low["student_id"], ""
            view = pd.DataFrame({
                "Name": low["Name"].fillna("(unknown)"),
                "Roll No": low["Roll No"].fillna(""),
                "Present/Total": low["present"].astype(int).astype(str) + "/" + low["total"].astype(int).astype(str),
                "Attendance %": low["pct"]})
            st.dataframe(view, hide_index=True, width="stretch")
            _dl(view, f"Below {thr}% - {sel}", sel, "section_defaulters", "secan_low")


# Backward-compatible name used by older imports (admin_screen.py, admin_analytics_hub.py)
show_section_analytics = section_analytics_tab
