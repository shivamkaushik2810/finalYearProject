"""Admin: substitution analytics and reports (Phase 8). Read-only."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from src.services import substitution_analytics as A
from src.services import substitution_analytics_service as AS
from src.services.report_export import df_pdf

IST = ZoneInfo("Asia/Kolkata")
EXPORT_COLUMNS = ["substitution_date", "section_code", "subject_code", "original_teacher_code",
                  "substitute_name", "status", "reasons"]


def _show(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def _table(rows, empty="None yet."):
    if not rows:
        st.caption(empty)
    else:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def show_substitution_analytics(admin_id, version_id):
    st.subheader("📊 Substitution analytics")
    today = datetime.now(IST).date()
    c1, c2 = st.columns(2)
    end = c2.date_input("To", value=today, key="sa_to")
    start = c1.date_input("From", value=today - timedelta(days=30), key="sa_from")
    try:
        rows, events = AS.load(admin_id, version_id, start, end)
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        return
    if not rows:
        st.info("No substitutions in this window.")
        return

    s = A.summary(rows)
    rates = A.decision_rates(events)
    speed = A.assignment_speed(rows, events)
    k = st.columns(5)
    k[0].metric("Substitutions", s["total"])
    k[1].metric("Assigned", f"{s['assigned_pct']}%")
    k[2].metric("Unassigned", f"{s['unassigned_pct']}%")
    k[3].metric("Acceptance", f"{rates['acceptance_rate']}%")
    k[4].metric("Avg minutes to assign",
                speed["avg_minutes"] if speed["avg_minutes"] is not None else "n/a")
    st.caption(f"Assignment speed is measured for {speed['measured']} of {speed['of']} substitutions "
               f"({speed['coverage_pct']}%). Confirmations made before the event log existed are not counted.")

    weeks = pd.DataFrame(A.by_week(rows))
    long = weeks.melt(id_vars="period", value_vars=["assigned", "unassigned"],
                      var_name="status", value_name="count")
    _show(alt.Chart(long).mark_bar().encode(
        x=alt.X("period:N", title="Week starting"),
        y=alt.Y("count:Q", title="Classes"),
        color=alt.Color("status:N", scale=alt.Scale(domain=["assigned", "unassigned"],
                                                     range=["#4F46E5", "#E11D48"])),
        tooltip=["period", "status", "count"]).properties(height=260))

    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**Most often absent**")
        _table(A.most_absent(rows))
        st.markdown("**Most used substitutes**")
        _table(A.most_used_substitutes(rows))
        st.markdown("**By subject**")
        _table(A.by_subject(rows))
    with t2:
        st.markdown("**Substitute workload (classes covered)**")
        _table(A.substitute_workload(rows))
        st.markdown("**Why classes went unassigned**")
        _table(A.unassigned_reasons(rows), "No unassigned classes in this window.")
        st.markdown("**Decisions**")
        st.caption(f"Accepted {rates['accepted']}, declined {rates['declined']}, "
                   f"confirmed {rates['confirmed']}, overridden {rates['overridden']}, "
                   f"rejected {rates['rejected']} (rejection rate {rates['rejection_rate']}%).")

    frame = pd.DataFrame([{c: r.get(c) for c in EXPORT_COLUMNS} for r in rows], columns=EXPORT_COLUMNS)
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ CSV", frame.to_csv(index=False).encode("utf-8"),
                       file_name=f"substitutions_{start}_{end}.csv", mime="text/csv", key="sa_csv")
    d2.download_button("⬇️ PDF", df_pdf(frame, "Substitution report", f"{start} to {end}"),
                       file_name=f"substitutions_{start}_{end}.pdf", mime="application/pdf", key="sa_pdf")
