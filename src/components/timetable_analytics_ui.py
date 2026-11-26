"""Analytics tab of the timetable editor. Read-only: it shows the version picked in the editor."""
import altair as alt
import pandas as pd
import streamlit as st

from src.components.timetable_views import DAY_SHORT
from src.database.config import supabase
from src.services import timetable_analytics as an


def _changes(vid):
    return (supabase.table("timetable_changes").select("*").eq("version_id", vid)
            .order("id", desc=True).limit(1000).execute().data or [])


def _substitutions(vid):
    return (supabase.table("faculty_substitutions")
            .select("status,original_teacher_code,substitution_date,period_no,subject_code,section_code")
            .eq("version_id", vid).limit(5000).execute().data or [])


def _label(e):
    return f"{e.section_code} {DAY_SHORT[e.weekday]} P{e.period_no} · {e.subject_code or e.kind}"


def _donut(rows, field, name):
    chart = (alt.Chart(pd.DataFrame(rows)).mark_arc(innerRadius=60)
             .encode(theta=f"{field}:Q", color=f"{name}:N", tooltip=[name, field]))
    st.altair_chart(chart)


def show_timetable_analytics(working, entries):
    st.caption("Read-only. Every figure is calculated from the version picked above. Nothing here changes the timetable.")
    if not entries:
        st.info("This version has no classes yet, so there is nothing to analyse.")
        return
    vid = working["id"]
    ov = an.overview(entries)

    st.markdown("**Overview**")
    c = st.columns(4)
    c[0].metric("Sections", ov["sections"])
    c[1].metric("Classes", ov["classes"])
    c[2].metric("Teachers", ov["teachers"])
    c[3].metric("Rooms in use", ov["rooms"])
    c = st.columns(4)
    c[0].metric("Periods scheduled", ov["periods"])
    c[1].metric("Teaching classes with no teacher", ov["unassigned"])
    c[2].metric("Clashes", ov["conflicts"])
    c[3].metric("Timetable completion", f"{ov['completion']}%")
    if ov["conflicts"]:
        st.error(f"{ov['conflicts']} clash(es) found. Fix them before making this version live.")
        labels = {e.id: _label(e) for e in entries}
        st.dataframe(pd.DataFrame([{"Class 1": labels.get(a), "Class 2": labels.get(b), "Clash": kind}
                                   for a, b, kind in an.clash_pairs(entries)]),
                     hide_index=True, width="stretch")
    else:
        st.success("No clashes found.")

    st.divider()
    st.markdown("**Faculty workload**")
    limit = st.number_input("Weekly teaching limit (periods)", min_value=1, max_value=60,
                            value=an.DEFAULT_WEEKLY_LIMIT, key=f"an_limit_{vid}")
    workload = an.faculty_workload(entries, weekly_limit=int(limit))
    if workload:
        stats = an.workload_stats(workload)
        c = st.columns(4)
        c[0].metric("Most periods", stats["max"])
        c[1].metric("Fewest periods", stats["min"])
        c[2].metric("Average periods", stats["average"])
        c[3].metric("Over the limit", stats["overloaded"])
        df = pd.DataFrame(workload)
        st.bar_chart(df.set_index("teacher")["periods"])
        st.dataframe(df.rename(columns={"teacher": "Teacher", "periods": "Periods/week", "classes": "Classes",
                                        "sections": "Sections", "free_periods": "Free periods",
                                        "overloaded": "Over limit", "subjects": "Subjects"}),
                     hide_index=True, width="stretch")

    st.divider()
    st.markdown("**Classroom utilisation**")
    rooms, _empty = an.room_usage(entries)
    if rooms:
        occupied = sum(r["periods"] for r in rooms)
        free = max(0, len(rooms) * an.SLOTS_PER_WEEK - occupied)
        c1, c2 = st.columns([1, 2])
        with c1:
            _donut([{"State": "Occupied", "Periods": occupied}, {"State": "Free", "Periods": free}],
                   "Periods", "State")
        with c2:
            st.dataframe(pd.DataFrame([{"Room": r["room"], "Classes": r["lectures"],
                                        "Periods used": r["periods"], "Utilisation %": r["utilisation"],
                                        "Underused": "yes" if r["underused"] else ""} for r in rooms]),
                         hide_index=True, width="stretch")
    else:
        st.info("No room is recorded on any class yet.")
    st.caption("Empty and maintenance rooms need a list of all rooms, which is not in the database yet. "
               "Only rooms that appear in this version are shown.")

    st.divider()
    st.markdown("**Peak periods**")
    peak = an.peak_periods(entries)
    if peak:
        st.bar_chart(pd.DataFrame({"Classes running": peak}).rename(index=lambda p: f"P{p}"))

    st.divider()
    st.markdown("**Sections**")
    secs = an.section_stats(entries)
    if secs:
        st.bar_chart(pd.DataFrame(secs).set_index("section")["completion"])
        st.dataframe(pd.DataFrame([{
            "Section": s["section"], "Classes": s["classes"], "Theory": s["theory"], "Lab": s["lab"],
            "Training": s["training"], "Activity": s["activity"], "Practical %": s["practical_share"],
            "Periods": s["periods"], "Free periods": s["free_periods"], "Completion %": s["completion"],
            "Periods per day": ", ".join(f"{DAY_SHORT[w]} {n}" for w, n in s["daily"].items()),
        } for s in secs]), hide_index=True, width="stretch")

    st.divider()
    st.markdown("**Changes and substitutions**")
    cs = an.change_summary(_changes(vid))
    c = st.columns(3)
    c[0].metric("Admin changes in this version", cs["total"])
    c[1].metric("Edits", cs["by_action"].get("update", 0))
    c[2].metric("Swaps", cs["by_action"].get("swap", 0))
    if cs["by_user"]:
        st.caption("By: " + ", ".join(f"{u} ({n})" for u, n in cs["by_user"].items()))
    if cs["most_changed"]:
        st.dataframe(pd.DataFrame(cs["most_changed"], columns=["Subject", "Changes"]),
                     hide_index=True, width="stretch")
    ss = an.substitution_summary(_substitutions(vid))
    c = st.columns(2)
    c[0].metric("Substitute assignments", ss["assigned"])
    c[1].metric("Substitution records", ss["total"])
    if ss["absent_teachers"]:
        st.dataframe(pd.DataFrame(ss["absent_teachers"], columns=["Teacher", "Times substituted"]),
                     hide_index=True, width="stretch")
