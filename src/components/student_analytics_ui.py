import hashlib
import io
import json
import math
import time
import zipfile

import pandas as pd
import streamlit as st

from src.database.config import supabase

from src.analytics.student_analytics import (
    AnalyticsConfig, DEFINITIONS, compute_all, subject_summary, export_tables,
    attendance_scenarios, prob_meet_target, build_llm_payload,
)
from src.components.analytics_charts import (
    CHART_TYPES, FIXED_WIDTH, build_chart, forecast_chart, marks_progress_chart, chart_png,
)
from src.database import analytics_db as adb
from src.services.report_export import sections_pdf
from src.analytics.ai_insights import interpret

LEVEL_ICON = {"good": "✅", "info": "ℹ️", "warn": "⚠️", "alert": "🚨"}


def _pct(v):
    return "N/A" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.1f}%"


def _show_chart(chart, stretch=True):
    if not stretch:
        st.altair_chart(chart)
        return
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def _log_error(where, e):
    print(f"Student analytics {where}: {type(e).__name__}")     # no student data in logs


# ───────────────────────── entry point ─────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def _directory():
    """Light list of every student's course / year / section (paged past the 1000-row cap)."""
    rows, start = [], 0
    while True:
        chunk = (supabase.table("students").select("student_id, course, year, section")
                 .order("student_id").range(start, start + 999).execute().data or [])
        rows.extend(chunk)
        if len(chunk) < 1000:
            return rows
        start += 1000


def _n(v):
    return str(v).strip().lower() if v not in (None, "") else ""


def _opts(rows, field):
    return sorted({str(r[field]).strip() for r in rows if r.get(field) not in (None, "")})


MAX_LIST = 300


def student_analytics_tab():
    st.header("🎓 Student Analytics")
    st.caption("Every figure is calculated from the database records of the selected student. "
               "Nothing here is sample data. Data may be up to 60 seconds old.")
    if not st.session_state.get("admin_data"):
        st.error("Administrator access required.")
        return
    try:
        sections = adb.get_sections()
        directory = _directory()
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        _log_error("sections", e)
        st.error("Could not load the class list. Please try again.")
        return
    if not sections:
        st.info("No students with a section were found.")
        return

    c1, c2 = st.columns(2)
    course = c1.selectbox("Course", ["All courses"] + _opts(directory, "course"), key="sa_course")
    pool = [d for d in directory if course == "All courses" or _n(d.get("course")) == _n(course)]
    year = c2.selectbox("Year", ["All years"] + _opts(pool, "year"), key="sa_year")
    pool = [d for d in pool if year == "All years" or _n(d.get("year")) == _n(year)]

    sec_counts = {}
    for d in pool:
        k = _n(d.get("section"))
        if k:
            sec_counts[k] = sec_counts.get(k, 0) + 1
    valid = {k: v for k, v in sections.items() if _n(k) in sec_counts}

    c3, c4 = st.columns(2)
    with c3:
        section_key = st.selectbox("Section", sorted(valid.keys()), index=None, placeholder="Select a section",
                                   format_func=lambda k: f"Section {k} ({sec_counts[_n(k)]} students)",
                                   key=f"sa_section_{course}_{year}")
    if not section_key:
        st.info("Select a course, year and section to begin.")
        return
    with c4:
        search = st.text_input("Search name or roll number", key=f"sa_search_{section_key}").strip().lower()

    allowed = {d["student_id"] for d in pool if _n(d.get("section")) == _n(section_key)}
    try:
        students = [x for x in adb.get_students(section_key) if x["student_id"] in allowed]
    except Exception as e:
        _log_error("students", e)
        st.error("Could not load students for this class.")
        return
    if search:
        students = [x for x in students if search in (x.get("name") or "").lower()
                    or search in str(x.get("roll_no") or "").lower()]
    if not students:
        st.warning("No students match these filters.")
        return
    if len(students) > MAX_LIST:
        st.caption(f"Showing the first {MAX_LIST} of {len(students)} students. Narrow the filters or use the search box.")
    cy = {d["student_id"]: d for d in directory}
    by_id = {x["student_id"]: {**x, "course": cy.get(x["student_id"], {}).get("course"),
                               "year": cy.get(x["student_id"], {}).get("year")} for x in students[:MAX_LIST]}

    student_id = st.selectbox("Student", list(by_id.keys()), index=None, placeholder="Select a student",
                              format_func=lambda i: f"{by_id[i]['name']} - {by_id[i].get('roll_no') or 'N/A'}",
                              key=f"sa_student_{section_key}_{course}_{year}_{search}")
    if student_id is None:
        st.info("Select a student to load their analytics.")
        return
    _render_student(section_key, student_id, by_id[student_id])


# ───────────────────────── student view ─────────────────────────

def _render_student(section_key, student_id, student):
    try:
        enrolled = adb.get_enrolled_subjects(section_key, student_id)
        marks_rows = adb.get_marks(section_key, student_id)
    except PermissionError:
        st.error("You do not have access to this student's records.")
        return
    except Exception as e:
        _log_error("student load", e)
        st.error("Could not load this student's records. Please try again.")
        return
    if not enrolled and not marks_rows:
        st.info("This student has no enrolled subjects or marks yet.")
        return

    subj_map = {s["subject_id"]: s for s in enrolled}
    exam_options = sorted({r.get("exam_type") for r in marks_rows if r.get("exam_type")})
    k = str(student_id)
    with st.expander("Filters and targets", expanded=True):
        f1, f2 = st.columns(2)
        sel_subjects = f1.multiselect("Subjects", list(subj_map.keys()), default=list(subj_map.keys()),
                                      format_func=lambda i: f"{subj_map[i]['name']} ({subj_map[i]['subject_code']})",
                                      key=f"sa_subj_{k}")
        sel_fac = f2.multiselect("Faculty", sorted({s["faculty"] for s in enrolled}), default=[],
                                 placeholder="All faculty", key=f"sa_fac_{k}")
        years = sorted({s.get("academic_year") for s in enrolled if s.get("academic_year")})
        sems = sorted({s.get("semester") for s in enrolled if s.get("semester") is not None})
        y1, y2 = st.columns(2)
        sel_year = y1.multiselect("Academic year", years, default=[], placeholder="All years", key=f"sa_year_{k}")
        sel_sem = y2.multiselect("Semester", sems, default=[], placeholder="All semesters", key=f"sa_sem_{k}")
        d1, d2, d3 = st.columns(3)
        start = d1.date_input("From", value=None, key=f"sa_from_{k}")
        end = d2.date_input("To", value=None, key=f"sa_to_{k}")
        sel_exam = d3.multiselect("Exam type", exam_options, default=[], placeholder="All exam types", key=f"sa_exam_{k}")
        t1, t2 = st.columns(2)
        att_target = t1.slider("Attendance target (%)", 50, 95, 75, 5, key=f"sa_att_t_{k}")
        marks_target = t2.slider("Marks target (%)", 30, 80, 50, 5, key=f"sa_mk_t_{k}")
        if not years and not sems:
            st.caption("No subject has an academic year or semester yet. Set them in Admin > Academic Terms.")

    chosen = [i for i in sel_subjects
              if (not sel_fac or subj_map[i]["faculty"] in sel_fac)
              and (not sel_year or subj_map[i].get("academic_year") in sel_year)
              and (not sel_sem or subj_map[i].get("semester") in sel_sem)]
    if not chosen:
        st.info("No subjects match the selected filters.")
        return
    if start and end and start > end:
        st.error("The 'From' date is after the 'To' date.")
        return
    all_selected = len(chosen) == len(subj_map)

    try:
        with st.spinner("Loading records..."):
            att_rows = adb.get_attendance(section_key, student_id, None if all_selected else chosen, start, end)
            section_agg = adb.get_section_marks_agg(section_key, None if all_selected else chosen, start, end, sel_exam or None)
            section_rows = [] if section_agg is not None else adb.get_section_marks(section_key)
    except Exception as e:
        _log_error("records", e)
        st.error("Could not load attendance and marks. Please try again.")
        return

    cfg = AnalyticsConfig(attendance_target=float(att_target), marks_target=float(marks_target))
    m = compute_all(att_rows, marks_rows, section_rows, [subj_map[i] for i in chosen], student_id, cfg,
                    start=start, end=end, subject_ids=None if all_selected else chosen, exam_types=sel_exam or None, section_agg=section_agg)

    st.markdown(f"### {student['name']}  ·  Roll {student.get('roll_no') or 'N/A'}  ·  {student.get('course') or ''} Year {student.get('year') or '-'}  ·  Section {section_key}")
    _kpis(m, cfg)

    t_over, t_chart, t_stat, t_trend, t_ins, t_exp = st.tabs(
        ["Overview", "Charts", "Statistics", "Trends and risk", "Insights", "Export"])
    with t_over:
        _overview(m)
    with t_chart:
        _charts(m, cfg, k)
    with t_stat:
        _statistics(m)
    with t_trend:
        _trends(m, cfg, k)
    with t_ins:
        _insights(m)
    with t_exp:
        _export(m, student, section_key, cfg)


def _kpis(m, cfg):
    a, mk, lat, comp = m["att"], m["marks"], m["latest"], m["completeness"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall attendance", _pct(a["pct"]),
              f"{a['present']}/{a['classes']} classes" if a["classes"] else None, delta_color="off",
              help=DEFINITIONS["Overall attendance %"])
    c2.metric("Overall marks", _pct(mk.get("weighted_pct")), f"{mk['n']} assessments" if mk["n"] else None,
              delta_color="off", help=DEFINITIONS["Overall marks %"])
    if lat:
        c3.metric(f"Latest: {lat['subject']} ({lat['exam_type']})", _pct(lat["pct"]), help=DEFINITIONS["Latest assessment"])
        c4.metric("Change vs previous", f"{lat['change']:+.1f} pts" if lat["change"] is not None else "N/A",
                  help=DEFINITIONS["Change vs previous"])
    else:
        c3.metric("Latest assessment", "N/A", help="Needs assessment dates (no date column or no dated marks).")
        c4.metric("Change vs previous", "N/A", help=DEFINITIONS["Change vs previous"])
    c5, c6, c7 = st.columns(3)
    sb = m["subjects_below"]
    names = ", ".join(sorted({s["subject"] for s in sb["attendance"]} | {s["subject"] for s in sb["marks"]})) or "none"
    c5.metric("Subjects below target", len({s["subject"] for s in sb["attendance"]} | {s["subject"] for s in sb["marks"]}),
              help=f"{DEFINITIONS['Subjects below target']} Currently: {names}")
    c6.metric("Data completeness", f"{comp['score']}%" if comp["score"] is not None else "N/A",
              help=DEFINITIONS["Data completeness"])
    last = max([x for x in (comp["last_attendance"], comp["last_marks"]) if x is not None], default=None)
    c7.metric("Last record", last.strftime("%d %b %Y") if last is not None else "N/A")


def _overview(m):
    st.subheader("Subject-wise summary")
    s = subject_summary(m["att_by_subject"], m["marks_by_subject"])
    if s.empty:
        st.info("No attendance or marks for the selected filters.")
    else:
        view = s.rename(columns={"subject": "Subject", "faculty": "Faculty", "classes": "Classes held", "present": "Present",
                                 "absent": "Absent", "attendance_pct": "Attendance %", "classes_needed": "Classes needed for target",
                                 "assessments": "Assessments", "marks_pct": "Marks %"})
        cols = [c for c in ["Subject", "Faculty", "Classes held", "Present", "Absent", "Attendance %",
                            "Classes needed for target", "Assessments", "Marks %"] if c in view.columns]
        st.dataframe(view[cols], hide_index=True, width="stretch")
    if not m["faculty"].empty:
        st.subheader("Faculty-wise attendance")
        st.dataframe(m["faculty"].rename(columns={"faculty": "Faculty", "classes": "Classes held", "present": "Present", "pct": "Attendance %"}),
                     hide_index=True, width="stretch")
    if not m["marks_by_exam"].empty:
        st.subheader("Marks by assessment type")
        st.dataframe(m["marks_by_exam"].rename(columns={"exam_type": "Exam type", "assessments": "Assessments", "pct": "Marks %"}),
                     hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        c1.caption("Internal vs external (external = End Term)")
        c1.dataframe(m["marks_categories"]["internal_external"].rename(columns={"group": "Group", "assessments": "Assessments", "pct": "Marks %"}),
                     hide_index=True, width="stretch")
        c2.caption("Theory vs practical")
        c2.dataframe(m["marks_categories"]["theory_practical"].rename(columns={"group": "Group", "assessments": "Assessments", "pct": "Marks %"}),
                     hide_index=True, width="stretch")
    comp = m["completeness"]
    with st.expander("Data completeness details"):
        st.write(f"- Selected subjects: {comp['selected_subjects']} (attendance: {comp['with_attendance']}, "
                 f"marks: {comp['with_marks']}, both: {comp['with_both']})")
        st.write(f"- Marks rows excluded as incomplete or invalid: {comp['marks_rows_excluded']}")
        st.write(f"- Attendance rows excluded (no valid time or subject): {comp['attendance_rows_dropped']}")
        st.write(f"- Excused classes left out: {comp.get('excused_excluded', 0)}; cancelled classes left out: {comp.get('cancelled_excluded', 0)}")
        st.write(f"- Unverified zero scores excluded until a teacher confirms them: {comp.get('unverified_marks', 0)}")
        st.write(f"- Scores of exactly 0 with no remarks in older data (possible placeholders): {comp['zero_scores_without_remarks']}")
        st.write(f"- Marks date column: {comp['marks_date_column'] or 'none found (no marks trends or date filter)'}")
    with st.expander("Definitions and formulas"):
        for name, text in DEFINITIONS.items():
            st.markdown(f"**{name}:** {text}")


def _charts(m, cfg, k):
    chosen = st.multiselect("Chart types (select one or more)", CHART_TYPES, default=["Bar", "Line"], key=f"sa_charts_{k}")
    if not chosen:
        st.info("Select at least one chart type.")
        return
    export_png = st.checkbox("Show PNG download buttons (slower)", key=f"sa_png_{k}")
    cols = st.columns(2)
    for i, kind in enumerate(chosen):
        with cols[i % 2]:
            res = build_chart(kind, m, cfg)
            st.markdown(f"**{kind}: {res['title']}**")
            if res["chart"] is None:
                st.info(res["note"])
            else:
                _show_chart(res["chart"], stretch=kind not in FIXED_WIDTH)
                if res["note"]:
                    st.caption(res["note"])
                if export_png:
                    png = chart_png(res["chart"])
                    if png:
                        st.download_button("⬇️ PNG", png, file_name=f"{kind.lower().replace(' ', '_')}.png",
                                           mime="image/png", key=f"sa_png_dl_{k}_{kind}")
                    else:
                        st.caption("PNG export is unavailable on this server.")


def _statistics(m):
    mk = m["marks"]
    st.subheader("Assessment statistics")
    if mk["n"] == 0:
        st.info("No scored assessments for the selected filters.")
    else:
        rows = [("Assessments (n)", mk["n"]), ("Mean %", mk["mean"]), ("Median %", mk["median"]), ("Minimum %", mk["min"]),
                ("Maximum %", mk["max"]), ("Range (points)", mk["range"])]
        for label, key in (("Mode %", "mode"), ("Standard deviation (sample)", "std"), ("Variance (sample)", "variance"),
                           ("Q1 %", "q1"), ("Q3 %", "q3"), ("IQR (points)", "iqr")):
            if key in mk:
                rows.append((label, mk[key]))
        st.dataframe(pd.DataFrame(rows, columns=["Statistic", "Value"]), hide_index=True, width="stretch")
        if mk.get("consistency"):
            st.caption(f"Consistency: {mk['consistency']} (standard deviation {mk['std']} points).")
        elif mk["n"] < 4:
            st.caption("Quartiles, outlier checks and a consistency rating need at least 4 assessments.")
        if mk["outliers"]:
            st.warning("Possible outliers (outside 1.5 x IQR): " +
                       "; ".join(f"{o['subject']} ({o['exam_type']}) {o['pct']}%" for o in mk["outliers"]))
    st.subheader("Attendance and marks")
    c = m["corr"]
    if c["status"] == "ok":
        a, b, d = st.columns(3)
        a.metric("Pearson r", c["pearson"], f"95% interval {c['ci_low']} to {c['ci_high']}", delta_color="off")
        b.metric("Spearman rho", c["spearman"])
        d.metric("Subjects (n)", c["n"])
        st.caption(f"A {c['strength']} association across subjects. Correlation does not show that attendance causes "
                   "higher or lower marks, and with this few observations the interval is wide.")
    else:
        st.info(f"Correlation not calculated: {c['reason']}")
    st.subheader("Comparison with the section")
    s = m["section"]
    if s["status"] != "ok":
        st.info(f"Not calculated: {s['reason']}")
    else:
        a, b, d, e = st.columns(4)
        a.metric("Student", _pct(s["student_pct"]))
        b.metric("Section mean", _pct(s["section_mean"]), f"SD {s['section_sd']}", delta_color="off")
        d.metric("z-score", s["z"] if s["z"] is not None else "N/A")
        e.metric("Percentile rank", f"{s['percentile']:.0f}")
        ps = s["per_subject"]
        if not ps.empty:
            t = m["marks_by_subject"][["subject_id", "subject", "marks_pct"]].merge(ps, on="subject_id")
            if not t.empty:
                st.dataframe(t.rename(columns={"subject": "Subject", "marks_pct": "Student marks %", "students": "Section students",
                                               "section_mean_pct": "Section mean %"}).drop(columns=["subject_id"]),
                              hide_index=True, width="stretch")
        st.caption("Compared with other students in the same section who have marks under the same filters.")


def _trends(m, cfg, k):
    st.subheader("Attendance over time")
    w = m["weekly"]
    if w.empty:
        st.info("No attendance records for the selected filters.")
    else:
        view = st.radio("Period", ["Weekly", "Monthly"], horizontal=True, key=f"sa_period_{k}")
        if view == "Weekly":
            t = w.assign(week=w["week"].dt.strftime("%d %b %Y"), pct=w["pct"].round(1), ma=w["ma"].round(1))
            st.dataframe(t.rename(columns={"week": "Week starting", "classes": "Classes", "present": "Present", "pct": "Attendance %",
                                           "ma": f"{cfg.ma_window}-week moving avg %"}), hide_index=True, width="stretch")
        else:
            mo = m["monthly"]
            st.dataframe(mo.assign(month=mo["month"].dt.strftime("%b %Y"), pct=mo["pct"].round(1))
                         .rename(columns={"month": "Month", "classes": "Classes", "present": "Present", "pct": "Attendance %"}),
                         hide_index=True, width="stretch")
    st.subheader("Consecutive absences")
    s = m["streaks"]
    if s.empty:
        st.info("No attendance records.")
    else:
        st.dataframe(s.rename(columns={"subject": "Subject", "longest": "Longest streak", "current": "Current streak"})
                     .drop(columns=["subject_id"]), hide_index=True, width="stretch")

    st.subheader("Marks progression")
    ch = marks_progress_chart(m, cfg)
    if ch is None:
        st.info("Marks trends need an assessment date. No dated marks were found.")
    else:
        _show_chart(ch)
        t = m["trend"]
        st.caption(f"Trend: {t['slope_per_30_days']:+.1f} points per 30 days ({t['note']})" if t["status"] == "ok"
                   else f"Trend not calculated: {t['reason']}")

    st.subheader("Attendance forecast")
    f = m["forecast"]
    if f["status"] != "ok":
        st.info(f"No forecast: {f['reason']}")
    else:
        _show_chart(forecast_chart(m))
        verdict = "better than" if f["beats_naive"] else "NOT better than"
        st.caption(f"Backtest on the last 3 weeks: mean absolute error {f['mae']} points, {verdict} a naive 'same as last week' "
                   f"forecast ({f['naive_mae']}). {f['note']}")
        if not f["beats_naive"]:
            st.warning("The trend forecast does not beat the naive forecast here, so treat it as indicative only.")

    st.subheader("Attendance risk")
    a = m["att"]
    if a["classes"] == 0:
        st.info("No attendance records for the selected filters.")
        return
    labels = {"critical": "🔴 Critical", "high": "🟠 High", "watch": "🟡 Watch", "low": "🟢 Low"}
    st.write(f"Rule-based risk band: **{labels.get(a['risk'], a['risk'])}** (attendance {_pct(a['pct'])} vs "
             f"{cfg.attendance_target:.0f}% target). This is a rule, not a probability.")
    remaining = st.number_input("Classes remaining in the term", 1, 300, 20, key=f"sa_rem_{k}")
    options = sorted({5, 10, 15, 20, int(remaining)})
    sc = attendance_scenarios(a["present"], a["classes"], cfg.attendance_target, options)
    st.dataframe(sc.rename(columns={"remaining_classes": "Remaining classes", "must_attend": "Must attend to reach target",
                                    "feasible": "Reachable", "pct_if_all_attended": "% if all attended",
                                    "pct_if_half_attended": "% if half attended", "pct_if_none_attended": "% if none attended"}),
                 hide_index=True, width="stretch")
    p = prob_meet_target(a["present"], a["classes"], int(remaining), cfg.attendance_target, cfg.min_prob_classes)
    if p is None:
        st.info(f"A probability estimate needs at least {cfg.min_prob_classes} classes held.")
    else:
        st.metric(f"Estimated chance of reaching {cfg.attendance_target:.0f}% after {int(remaining)} more classes", f"{p * 100:.0f}%",
                  help=DEFINITIONS["Probability of meeting target"])
        st.caption("Model-based estimate (beta-binomial, uniform prior) assuming future classes behave like past ones. "
                   "It is not calibrated or validated and ignores illness, exams and other causes.")
    st.info("Likelihood of reaching a marks target is not available: there is no validated model and too few assessments per student.")


def _insights(m):
    st.caption("Rule-based insights come first. Each card lists the evidence it is based on.")
    for ins in m["insights"]:
        with st.container(border=True):
            st.markdown(f"**{LEVEL_ICON.get(ins['level'], 'ℹ️')} {ins['title']}**")
            st.write(ins["text"])
            with st.expander("Evidence"):
                for e in ins["evidence"]:
                    st.write(f"- {e}")
            if ins["next_step"]:
                st.caption(f"Suggested next step: {ins['next_step']}")
    st.divider()
    _ai_section(m)


def _ai_section(m):
    st.subheader("🤖 AI interpretation")
    st.caption("An AI model rewrites the verified metrics as plain-language findings. It receives no name, roll number, "
               "faculty or IDs. Every card must cite verified facts and may not contain a number that is not in them; "
               "cards that fail the check are dropped.")
    payload = build_llm_payload(m)
    sig = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    key = f"sa_ai_{sig}"
    if st.button("Generate AI interpretation", key=f"{key}_btn", icon=":material/auto_awesome:"):
        if time.time() - st.session_state.get("sa_ai_last", 0) < 8:
            st.warning("Please wait a few seconds before generating again.")
        else:
            st.session_state["sa_ai_last"] = time.time()
            with st.spinner("Interpreting the verified metrics..."):
                st.session_state[key] = interpret(payload)
    res = st.session_state.get(key)
    if res:
        if res["status"] == "unavailable":
            st.info(res["message"])
        elif res["status"] == "error":
            st.error(res["message"])
        else:
            for c in res["cards"]:
                with st.container(border=True):
                    st.markdown(f"**{LEVEL_ICON.get(c['level'], 'ℹ️')} {c['title']}** · AI-generated")
                    st.write(c["text"])
                    with st.expander("Verified facts it relies on"):
                        for e in c["evidence"]:
                            st.write(f"- {e}")
                    if c["next_step"]:
                        st.caption(f"Suggested next step: {c['next_step']}")
            if not res["cards"]:
                st.info("The AI returned nothing that passed the verification check.")
            st.caption(f"Model: {res['model']} · {res['rejected']} card(s) rejected by the verification check.")
    with st.expander("Exactly what is sent to the model"):
        st.json(payload)


def _charts_zip(m, cfg):
    buf, n = io.BytesIO(), 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, kind in enumerate(CHART_TYPES, 1):
            res = build_chart(kind, m, cfg)
            png = chart_png(res["chart"]) if res["chart"] is not None else None
            if png:
                z.writestr(f"{i:02d}_{kind.lower().replace(' ', '_')}.png", png)
                n += 1
        for name, ch in (("forecast", forecast_chart(m)), ("marks_progress", marks_progress_chart(m, cfg))):
            png = chart_png(ch) if ch is not None else None
            if png:
                z.writestr(f"{name}.png", png)
                n += 1
    return buf.getvalue() if n else None


def _export(m, student, section_key, cfg):
    sid = student["student_id"]
    tables = export_tables(m)
    meta = m["meta"]
    sig = hashlib.sha1(json.dumps([sid, meta["period_start"], meta["period_end"], meta["start_filter"], meta["end_filter"],
                                   meta["exam_types"], m["att"]["classes"], m["att"]["present"], m["marks"]["n"],
                                   m["marks"].get("weighted_pct"), cfg.attendance_target, cfg.marks_target],
                                  default=str).encode()).hexdigest()
    c1, c2 = st.columns(2)
    with c1:
        name = st.selectbox("CSV dataset", list(tables.keys()), key=f"sa_csv_{sid}")
        df = tables[name]
        if df is None or df.empty:
            st.info("This dataset is empty for the selected filters.")
        else:
            st.dataframe(df.head(10), hide_index=True, width="stretch")
            st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name=f"{name.lower().replace(' ', '_')}.csv", mime="text/csv", key=f"sa_csvdl_{sid}")
    with c2:
        st.write("**PDF report** (tables, charts, insights, formulas and limitations)")
        pk = f"sa_pdf_{sid}"
        if st.button("Prepare PDF report", key=f"{pk}_btn"):
            with st.spinner("Building the report..."):
                st.session_state[pk] = (sig, _build_pdf(m, student, section_key, cfg))
        ready = st.session_state.get(pk)
        if ready and ready[0] == sig:
            st.download_button("⬇️ Download PDF report", ready[1],
                               file_name=f"student_analytics_{student.get('roll_no') or sid}.pdf",
                               mime="application/pdf", key=f"{pk}_dl")
    st.divider()
    st.write("**Chart images (PNG)**")
    zk = f"sa_zip_{sid}"
    if st.button("Prepare all chart images (ZIP)", key=f"{zk}_btn"):
        with st.spinner("Rendering charts..."):
            st.session_state[zk] = (sig, _charts_zip(m, cfg))
    ready = st.session_state.get(zk)
    if ready and ready[0] == sig:
        if ready[1] is None:
            st.warning("No chart image could be produced (no chart has enough data, or image export is unavailable).")
        else:
            st.download_button("⬇️ Download chart images (ZIP)", ready[1], file_name=f"charts_{student.get('roll_no') or sid}.zip",
                               mime="application/zip", key=f"{zk}_dl")


def _build_pdf(m, student, section_key, cfg):
    a, mk, meta = m["att"], m["marks"], m["meta"]
    meta_lines = [
        f"Student: {student['name']} (Roll {student.get('roll_no') or 'N/A'}), Section {section_key}",
        f"Attendance period: {meta['period_start'] or 'n/a'} to {meta['period_end'] or 'n/a'}",
        f"Filters: from {meta['start_filter'] or 'any'} to {meta['end_filter'] or 'any'}; exam types: "
        f"{', '.join(meta['exam_types']) or 'all'}",
        f"Targets: attendance {cfg.attendance_target:.0f}%, marks {cfg.marks_target:.0f}%",
    ]
    kpi_rows = [["Overall attendance", _pct(a["pct"]), f"{a['present']}/{a['classes']} classes held"],
                ["Overall marks", _pct(mk.get("weighted_pct")), f"{mk['n']} scored assessments"],
                ["Attendance risk band", a["risk"], "Rule-based"]]
    s = subject_summary(m["att_by_subject"], m["marks_by_subject"])
    subj_rows = [] if s.empty else [[r.get("subject"), r.get("classes", ""), r.get("present", ""), r.get("attendance_pct", ""),
                                     r.get("assessments", ""), r.get("marks_pct", "")] for r in s.to_dict("records")]
    md = m["marks_df"]
    mark_rows = [] if md.empty else [[r["subject"], r["exam_type"], f"{r['obtained']:g}/{r['max_marks']:g}", f"{r['pct']:.1f}%",
                                      r["when"].strftime("%d %b %Y") if pd.notna(r["when"]) else "n/a"] for _, r in md.iterrows()]
    insight_lines = []
    for i in m["insights"]:
        insight_lines.append(f"{i['title']}: {i['text']}")
        insight_lines += [f"   Evidence: {e}" for e in i["evidence"]]
    chart_secs = []
    for kind in ("Bar", "Line", "Scatter"):
        res = build_chart(kind, m, cfg)
        png = chart_png(res["chart"]) if res["chart"] is not None else None
        if png:
            chart_secs.append({"heading": f"Chart: {res['title']}", "image": png})
    sections = [
        {"heading": "Key metrics", "headers": ["Metric", "Value", "Basis"], "rows": kpi_rows},
        {"heading": "Subject-wise summary", "headers": ["Subject", "Classes", "Present", "Attendance %", "Assessments", "Marks %"], "rows": subj_rows},
        {"heading": "Assessments", "headers": ["Subject", "Exam", "Marks", "Percent", "Date"], "rows": mark_rows},
        {"heading": "Insights (rule-based, from verified metrics)", "lines": insight_lines or ["No insights."]},
        {"heading": "Definitions", "lines": [f"{k}: {v}" for k, v in DEFINITIONS.items()]},
        {"heading": "Limitations", "lines": [
            "Excused absences are excluded from the denominator and cancelled classes are never counted (policy: exclude).",
            "Missing marks are excluded, never treated as zero; unverified zero scores are excluded until confirmed.",
            "Correlation is an association, not causation; small samples give wide uncertainty.",
            "Risk bands are rules. Probabilities are model estimates under stated assumptions and are not validated."]},
    ]
    return sections_pdf("Student Analytics Report", meta_lines, sections[:1] + chart_secs + sections[1:])
