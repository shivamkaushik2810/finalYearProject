"""Admin timetable editor. One page, five tabs. Students and teachers see only the LIVE version.
Adding a class, changing a class and choosing its teacher all happen in one 'Classes' tab."""
from dataclasses import replace

import pandas as pd
import streamlit as st

from src.components.timetable_analytics_ui import show_timetable_analytics
from src.components.timetable_views import DAY_SHORT, all_sections_html, section_sort_key, teacher_matrix_html
from src.database.config import supabase
from src.services import published_timetable as pt
from src.services import timetable_blank as tb
from src.services import timetable_draft as td
from src.services import timetable_service as svc
from src.services.timetable_validator import DAYS, KINDS, PERIODS
from src.services.timetable_workload import workload_report

FIELDS = ("weekday", "period_no", "block_len", "kind",
          "subject_code", "subject_name", "faculty_code", "room")
RECENT_CHANGE_LIMIT = 500
STATUS_TEXT = {"published": "LIVE", "draft": "draft", "archived": "archived"}
NO_TEACHER = "(none - activity)"


# ---------- helpers ----------

def _values(e):
    return {k: getattr(e, k) for k in FIELDS}


def _clean(text):
    text = (text or "").strip()
    return text or None


def _actor(admin_id):
    return (st.session_state.get("admin_data") or {}).get("username") or str(admin_id)


def _label(r):
    return f"{r['label']}  [{STATUS_TEXT.get(r['status'], r['status'])}]"


def _entry_label(e):
    return f"{e.section_code}  {DAY_SHORT[e.weekday]}  P{e.period_no}  ·  {e.subject_code or e.kind}"


def _workload_table(entries):
    teachers = sorted({e.faculty_code for e in entries if e.faculty_code})
    report = workload_report(entries, teachers)
    df = pd.DataFrame(report["rows"]).rename(columns={
        "faculty": "Faculty", "periods": "Periods/week", "hours": "Hours/week",
        "vs_target": "vs target", "status": "Status"})
    return report, df


def _all_versions():
    return (supabase.table("timetable_versions").select("id,label,status,created_at")
            .order("id").execute().data or [])


def _working_choices():
    rows = [r for r in _all_versions() if r["status"] in ("published", "draft")]
    rows.sort(key=lambda r: (r["status"] != "published", r["id"]))
    return rows


def _id_for_label(name):
    rows = supabase.table("timetable_versions").select("id").eq("label", name).execute().data or []
    return rows[0]["id"] if rows else None


def _recent_changes(vid):
    rows = svc.list_changes(vid, limit=RECENT_CHANGE_LIMIT)
    return [h for h in rows if h.get("changed_by") != "import"]


def _switch_to(vid):
    if vid is not None:
        st.session_state["tte_work_next"] = vid
    st.rerun()


def _teacher_options(current=None):
    """Teacher codes from the database, with a 'no teacher' choice for activities.
    A code already on a class is kept in the list even if it is not in the teacher table."""
    rows = supabase.table("teacher_codes").select("code").order("code").execute().data or []
    codes = sorted({r["code"] for r in rows if r.get("code")})
    if current and current not in codes:
        codes.append(current)
    return [NO_TEACHER] + codes


def _version_picker():
    rows = _working_choices()
    if not rows:
        return None
    by_id = {r["id"]: r for r in rows}
    pending = st.session_state.pop("tte_work_next", None)
    if pending in by_id:
        st.session_state["tte_work_id"] = pending
    if st.session_state.get("tte_work_id") not in by_id:
        st.session_state.pop("tte_work_id", None)
    chosen = st.selectbox("Version you are working on", list(by_id), key="tte_work_id",
                          format_func=lambda i: _label(by_id[i]),
                          help="Students and teachers see only the LIVE version. Drafts stay private until made live.")
    return by_id[chosen]


# ---------- tab: timetable (view) ----------

def _tab_timetable(working, entries):
    if not entries:
        st.info("This version has no classes yet. Open the Classes tab to add some.")
        return
    vid = working["id"]
    slot_times = svc.list_period_slots()
    changed_ids = {h["entry_id"] for h in _recent_changes(vid)}
    codes = sorted({e.section_code for e in entries}, key=section_sort_key)
    teachers = sorted({e.faculty_code for e in entries if e.faculty_code})
    c1, c2 = st.columns(2)
    sec = c1.selectbox("Section", ["All sections"] + codes, key=f"tte_view_sec_{vid}")
    tea = c2.selectbox("Teacher", ["All teachers"] + teachers, key=f"tte_view_tea_{vid}")
    shown = entries
    if sec != "All sections":
        shown = [e for e in shown if e.section_code == sec]
    if tea != "All teachers":
        shown = [e for e in shown if e.faculty_code == tea]
    if not shown:
        st.info("Nothing matches these filters.")
        return
    if changed_ids & {e.id for e in shown}:
        st.caption("Orange border = changed by an admin in this version.")
    st.markdown(all_sections_html(shown, slot_times, changed_ids=changed_ids), unsafe_allow_html=True)
    st.markdown("**Teachers: weekly teaching periods**")
    st.markdown(teacher_matrix_html(shown), unsafe_allow_html=True)
    with st.expander("Workload across this version"):
        report, table = _workload_table(entries)
        st.caption(f"Target = equal share of the teachers in this version: {report['target_periods']} periods/week.")
        st.dataframe(table, hide_index=True, width="stretch")
        if report["unlisted"]:
            st.warning("Teaching entries use codes that are not in the teacher list: " + ", ".join(report["unlisted"]))


# ---------- tab: classes (add, change, teacher) ----------

def _add_form(admin_id, vid):
    secs = tb.list_sections()
    if not secs:
        st.info("No active sections exist yet.")
        return
    codes = {s["code"]: s["id"] for s in secs}
    teachers = _teacher_options()
    with st.form(f"tte_add_form_{vid}"):
        c1, c2, c3, c4 = st.columns(4)
        sec = c1.selectbox("Section", list(codes), key=f"tte_add_sec_{vid}")
        day = c2.selectbox("Day", list(DAYS), format_func=lambda d: DAY_SHORT[d], key=f"tte_add_day_{vid}")
        period = c3.selectbox("Start period", list(PERIODS), key=f"tte_add_p_{vid}")
        block = c4.number_input("Periods long", min_value=1, max_value=4, value=1, key=f"tte_add_b_{vid}")
        c5, c6 = st.columns(2)
        kind = c5.selectbox("Kind", list(KINDS), key=f"tte_add_k_{vid}")
        teacher = c6.selectbox("Teacher", teachers, key=f"tte_add_t_{vid}")
        c7, c8, c9 = st.columns(3)
        subject_code = c7.text_input("Subject code", key=f"tte_add_sc_{vid}")
        subject_name = c8.text_input("Subject name", key=f"tte_add_sn_{vid}")
        room = c9.text_input("Room", key=f"tte_add_r_{vid}")
        save = st.form_submit_button("Save this class", type="primary")
    if save:
        try:
            tb.add_entry(_actor(admin_id), vid, {
                "section_id": codes[sec], "weekday": day, "period_no": period, "block_len": block,
                "kind": kind, "subject_code": subject_code.strip(), "subject_name": subject_name.strip(),
                "faculty_code": "" if teacher == NO_TEACHER else teacher, "room": room.strip()})
        except td.DraftError as exc:
            st.error(str(exc))
        else:
            st.toast(f"Saved: {sec} {DAY_SHORT[day]} P{period}.")
            st.rerun()


def _edit_form(admin_id, vid, entries):
    ordered = sorted(entries, key=lambda e: (section_sort_key(e.section_code), e.weekday, e.period_no))
    choices = {_entry_label(e): e for e in ordered}
    target = choices[st.selectbox("Class to change", list(choices), key=f"tte_pick_{vid}")]
    current = target.faculty_code
    teachers = _teacher_options(current)
    default_teacher = current or NO_TEACHER
    k = f"{vid}_{target.id}"

    with st.form(f"tte_edit_form_{k}"):
        c1, c2, c3 = st.columns(3)
        weekday = c1.selectbox("Day", list(DAYS), index=list(DAYS).index(target.weekday),
                               format_func=lambda d: DAY_SHORT[d], key=f"tte_e_day_{k}")
        period_no = c2.selectbox("Start period", list(PERIODS),
                                 index=list(PERIODS).index(target.period_no), key=f"tte_e_p_{k}")
        block_len = c3.number_input("Periods long", min_value=1, max_value=4,
                                    value=target.block_len, key=f"tte_e_b_{k}")
        c4, c5 = st.columns(2)
        kind = c4.selectbox("Kind", list(KINDS), index=list(KINDS).index(target.kind), key=f"tte_e_k_{k}")
        teacher = c5.selectbox("Teacher", teachers, index=teachers.index(default_teacher), key=f"tte_e_t_{k}")
        c6, c7, c8 = st.columns(3)
        subject_code = c6.text_input("Subject code", value=target.subject_code or "", key=f"tte_e_sc_{k}")
        subject_name = c7.text_input("Subject name", value=target.subject_name or "", key=f"tte_e_sn_{k}")
        room = c8.text_input("Room", value=target.room or "", key=f"tte_e_r_{k}")
        b1, b2 = st.columns(2)
        check = b1.form_submit_button("Check")
        save = b2.form_submit_button("Save change", type="primary")

    changes = {
        "weekday": int(weekday), "period_no": int(period_no), "block_len": int(block_len),
        "kind": kind, "subject_code": _clean(subject_code), "subject_name": _clean(subject_name),
        "faculty_code": None if teacher == NO_TEACHER else teacher, "room": _clean(room),
    }
    proposed = replace(target, **changes)
    new_entries = [proposed if e.id == target.id else e for e in entries]

    errors = []
    if check or save:
        _, errors = svc.check_change(admin_id, vid, target.id, changes)
        if errors:
            st.error("Not saved:\n\n- " + "\n- ".join(errors))
        elif check:
            st.success("No problems found with this change.")

    if save and not errors:
        res = svc.apply_change(admin_id, vid, target.id, changes, _actor(admin_id), expected=_values(target))
        if res["ok"]:
            st.toast("Saved.")
            st.rerun()
        else:
            st.error("Not saved. Someone else may have changed this class. Choose it again and re-apply.\n\n- "
                     + "\n- ".join(res["errors"]))

    faculties = sorted({f for f in (current, proposed.faculty_code) if f})
    if faculties:
        before, _ = _workload_table(entries)
        after, _ = _workload_table(new_entries)
        before_rows = {r["faculty"]: r["periods"] for r in before["rows"]}
        after_rows = {r["faculty"]: r["periods"] for r in after["rows"]}
        st.caption("Teacher workload if you save this change (periods per week)")
        st.dataframe(pd.DataFrame([{"Teacher": f, "Before": before_rows.get(f, 0), "After": after_rows.get(f, 0)}
                                   for f in faculties]), hide_index=True)


def _apply_teacher(admin_id, vid, matching, new_code):
    actor = _actor(admin_id)
    problems = []
    for e in matching:
        _, errors = svc.check_change(admin_id, vid, e.id, {**_values(e), "faculty_code": new_code})
        problems += [f"{_entry_label(e)}: {msg}" for msg in errors]
    if problems:
        st.error("Nothing was changed. Fix these first:\n\n- " + "\n- ".join(problems))
        return
    for done, e in enumerate(matching, start=1):
        res = svc.apply_change(admin_id, vid, e.id, {**_values(e), "faculty_code": new_code},
                               actor, expected=_values(e))
        if not res["ok"]:
            st.error(f"Stopped after {done - 1} of {len(matching)} class(es). {_entry_label(e)} was not saved: "
                     + "; ".join(res["errors"]) + ". Reload the page and check the list.")
            return
    st.toast(f"Teacher set on {len(matching)} class(es).")
    st.rerun()


def _bulk_teacher(admin_id, vid, working, entries):
    with st.expander("Give one teacher every class of a subject in one section"):
        st.caption("Choose a section, a subject and a teacher. Every class of that subject in that section gets "
                   "the teacher. All classes are checked first; if one fails, nothing is changed.")
        codes = sorted({e.section_code for e in entries}, key=section_sort_key)
        c1, c2, c3 = st.columns(3)
        sec = c1.selectbox("Section", codes, key=f"tte_bulk_sec_{vid}")
        subjects = sorted({e.subject_code for e in entries if e.section_code == sec and e.subject_code})
        if not subjects:
            st.info("This section has no subject codes.")
            return
        subj = c2.selectbox("Subject", subjects, key=f"tte_bulk_subj_{vid}_{sec}")
        teacher = c3.selectbox("Teacher", _teacher_options(), key=f"tte_bulk_t_{vid}")
        matching = [e for e in entries if e.section_code == sec and e.subject_code == subj]
        st.write(f"{len(matching)} class(es) will get: **{'no teacher' if teacher == NO_TEACHER else teacher}**")
        confirm = True
        if working["status"] == "published":
            confirm = st.checkbox("I understand this changes the LIVE timetable straight away",
                                  key=f"tte_bulk_live_{vid}")
        if st.button("Check, then apply", type="primary", disabled=not (confirm and matching),
                     key=f"tte_bulk_btn_{vid}"):
            _apply_teacher(admin_id, vid, matching, None if teacher == NO_TEACHER else teacher)


def _tab_classes(admin_id, working, entries):
    vid = working["id"]
    st.markdown("**What do you want to do?**")
    mode = st.radio("What do you want to do?", ["Add a new class", "Change an existing class"],
                    horizontal=True, label_visibility="collapsed", key=f"tte_mode_{vid}")
    if mode == "Add a new class":
        st.caption("Fill in the whole class, including its teacher, then save it once.")
        _add_form(admin_id, vid)
    else:
        if not entries:
            st.info("There are no classes to change yet. Choose 'Add a new class' first.")
        else:
            st.caption("The form shows the class as it is now. Check it, then save.")
            _edit_form(admin_id, vid, entries)
    if entries:
        st.divider()
        _bulk_teacher(admin_id, vid, working, entries)


# ---------- tab: versions and go live ----------

def _tab_versions(admin_id, live, working):
    st.markdown("**1. Create a new version**")
    st.caption("A new version is private. Students and teachers see it only after you make it live (step 2).")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("Copy of the live timetable")
        copy_name = st.text_input("Name for the copy", value=f"{live['label']}-copy" if live else "",
                                  key="tte_copy_name").strip()
        if st.button("Create copy", type="primary", disabled=live is None, key="tte_copy_btn"):
            try:
                td.create_draft(admin_id, live["id"], copy_name)
            except td.DraftError as exc:
                st.error(str(exc))
            else:
                _switch_to(_id_for_label(copy_name))
    with c2:
        st.markdown("Empty timetable (fill it yourself)")
        blank_name = st.text_input("Name for the empty version", key="tte_blank_name").strip()
        if st.button("Create empty version", key="tte_blank_btn"):
            try:
                tb.create_blank_version(_actor(admin_id), blank_name)
            except td.DraftError as exc:
                st.error(str(exc))
            else:
                _switch_to(_id_for_label(blank_name))

    st.divider()
    st.markdown("**2. Make the working version live**")
    if working["status"] == "published":
        st.info(f"'{working['label']}' is already the live timetable.")
    else:
        st.warning("Making a version live replaces the current live timetable for everyone at once. "
                   "The old live version is archived, not deleted. Check the grid in the Timetable tab first.")
        ok = st.checkbox(f"I have checked '{working['label']}' and want it to replace the live timetable",
                         key=f"tte_live_ok_{working['id']}")
        if st.button("Make live", type="primary", disabled=not ok, key=f"tte_live_btn_{working['id']}"):
            try:
                pt.publish_version(admin_id, working["id"])
            except (pt.PublishError, PermissionError) as exc:
                st.error(str(exc))
            else:
                st.toast(f"'{working['label']}' is now live.")
                _switch_to(working["id"])

    st.divider()
    st.markdown("**All versions**")
    st.dataframe(pd.DataFrame([{"Name": r["label"], "Status": STATUS_TEXT.get(r["status"], r["status"]),
                                "Created": r["created_at"]} for r in _all_versions()]),
                 hide_index=True, width="stretch")


# ---------- tab: history ----------

def _tab_history(working):
    rows = _recent_changes(working["id"])
    if not rows:
        st.caption("No changes by admins in this version yet.")
        return
    st.dataframe(pd.DataFrame([{"When": h["changed_at"], "Class": h["entry_id"], "By": h["changed_by"],
                                "Action": h.get("action", "")} for h in rows[:200]]),
                 hide_index=True, width="stretch")


# ---------- page ----------

def show_timetable_editor():
    admin = st.session_state.get("admin_data") or {}
    admin_id = admin.get("id")
    try:
        svc.require_admin(admin_id)
    except PermissionError as exc:
        st.error(str(exc))
        return

    st.subheader("🗓️ Timetable editor")
    working = _version_picker()
    if not working:
        st.info("No timetable version exists yet.")
        return
    live = pt.published_version()
    if working["status"] == "published":
        st.success(f"'{working['label']}' is LIVE. Students and teachers see every change here straight away.")
    else:
        st.info(f"'{working['label']}' is a draft. Students and teachers do not see it until you make it live "
                "(Versions and go live tab).")
    st.caption(f"Live now: {live['label']}" if live else "No live timetable yet.")

    entries = svc.load_entries(working["id"])
    t_view, t_classes, t_versions, t_history, t_analytics = st.tabs([
        "Timetable", "Classes", "Versions and go live", "History", "Analytics"])
    with t_view:
        _tab_timetable(working, entries)
    with t_classes:
        _tab_classes(admin_id, working, entries)
    with t_versions:
        _tab_versions(admin_id, live, working)
    with t_history:
        _tab_history(working)
    with t_analytics:
        show_timetable_analytics(working, entries)
