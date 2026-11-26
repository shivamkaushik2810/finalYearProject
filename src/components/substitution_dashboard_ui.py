"""Admin: faculty substitution dashboard (Phase 5). Admin-only. Proposes, confirms and rejects
substitutions and edits the scoring weights. Never changes the permanent timetable."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.services import substitution_service as svc
from src.services import substitution_manual_service as msvc
from src.services.substitution_notify import notify_assigned
from src.components.substitution_analytics_ui import show_substitution_analytics
from src.services.substitution_dashboard_rules import day_kpis
from src.services.substitution_scoring import CRITERIA
from src.services.timetable_service import get_version as get_timetable_version, require_admin

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_LABEL = "import-3D-VI"


def show_substitution_dashboard():
    st.subheader("🔁 Faculty substitution")
    admin_id = (st.session_state.get("admin_data") or {}).get("id")
    try:
        require_admin(admin_id)
    except PermissionError as exc:
        st.error(str(exc))
        return

    label = st.text_input("Draft version", value=DEFAULT_LABEL, key="fs_label").strip()
    try:
        version = get_timetable_version(label)
    except LookupError as exc:
        st.error(str(exc))
        return
    on_date = st.date_input("Date", value=datetime.now(IST).date(), key="fs_date")

    if st.button("Auto assign for this date", type="primary", key="fs_plan"):
        try:
            res = svc.plan_substitutions(admin_id, version["id"], on_date)
        except (svc.SubstitutionError, PermissionError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:
            print(f"substitution planning failed: {type(exc).__name__}")
            st.error("Planning failed. See the terminal log.")
        else:
            for w in res["warnings"]:
                st.warning(w)
            if res.get("note"):
                st.info(res["note"])
            else:
                st.success(f"Planned {res['slots']} class(es): {res['assigned']} proposed, "
                           f"{res['unassigned']} unassigned. Proposals need your confirmation.")

    try:
        rows = svc.list_day(admin_id, version["id"], on_date)
        absent = svc.absent_teacher_count(on_date)
    except (svc.SubstitutionError, PermissionError) as exc:
        st.error(str(exc))
        return
    k = day_kpis(rows, absent)
    cols = st.columns(6)
    cols[0].metric("Absent teachers", k["absent_teachers"])
    cols[1].metric("Classes to cover", k["requiring"])
    cols[2].metric("Assigned", k["assigned"])
    cols[3].metric("Pending approval", k["pending"])
    cols[4].metric("Unassigned", k["unassigned"])
    cols[5].metric("Completion", f"{k['completion']}%")

    if not rows:
        st.info("No substitution rows for this date. Run Auto assign once an approved absence exists.")
    else:
        st.dataframe(pd.DataFrame([{
            "Period": f"P{r['period_no']}", "Section": r["section_code"], "Subject": r["subject_code"],
            "Room": r.get("room") or "", "Original": r["original_teacher_code"],
            "Replacement": r.get("substitute_name") or "—", "Method": "Auto",
            "Status": r["status"], "Score": "" if r.get("score") is None else r["score"],
        } for r in rows]), hide_index=True, width="stretch")

    st.markdown("**Confirm or reject a proposal**")
    proposed = [r for r in rows if r["status"] == "proposed"]
    if not proposed:
        st.caption("No proposals are waiting for confirmation.")
    else:
        choices = {f"P{r['period_no']} {r['section_code']} {r['subject_code']} → {r['substitute_name']}": r
                   for r in proposed}
        pick = choices[st.selectbox("Proposal", list(choices), key="fs_pick")]
        b1, b2 = st.columns(2)
        if b1.button("Confirm", type="primary", key="fs_confirm"):
            try:
                svc.confirm_substitution(admin_id, pick["id"])
            except (svc.SubstitutionError, PermissionError) as exc:
                st.error(str(exc))
            else:
                warn = notify_assigned(pick["id"])
                if warn:
                    st.warning(warn)
                st.toast("Confirmed.")
                st.rerun()
        if b2.button("Reject", key="fs_reject"):
            try:
                svc.reject_substitution(admin_id, pick["id"])
            except (svc.SubstitutionError, PermissionError) as exc:
                st.error(str(exc))
            else:
                st.toast("Rejected. The class is now unassigned.")
                st.rerun()
        with st.expander("Why this teacher? (score and alternatives)"):
            st.write("Factors (0 to 1):", pick.get("factors") or "no scoring data")
            st.write("Next-best candidates:", pick.get("alternatives") or "none")

    st.divider()
    st.subheader("Change substitute")
    editable = [r for r in rows if r["status"] in ("proposed", "assigned", "unassigned")]
    if not editable:
        st.caption("Nothing to change for this date.")
    else:
        labels = {f"P{r['period_no']} {r['section_code']} {r['subject_code']} (now: "
                  f"{r.get('substitute_name') or 'none'})": r for r in editable}
        target = labels[st.selectbox("Class", list(labels), key="fs_ov_row")]
        try:
            options = msvc.candidate_options(admin_id, version["id"], target["id"])
        except (msvc.ManualError, PermissionError) as exc:
            st.error(str(exc))
            options = []
        if options:
            opt_labels = {("✓ " if o["eligible"] else "✗ ") + f"{o['code']} {o['name']}": o
                          for o in options}
            chosen = opt_labels[st.selectbox("New substitute", list(opt_labels), key="fs_ov_teacher")]
            if chosen["reasons"]:
                st.warning("Not eligible: " + "; ".join(chosen["reasons"]))
            force = False
            if not chosen["eligible"]:
                force = st.checkbox("Override anyway (recorded in history)", key="fs_ov_force")
            reason = st.text_input("Reason for the change (required)", max_chars=300, key="fs_ov_reason")
            if st.button("Change substitute", type="primary", key="fs_ov_go"):
                try:
                    msvc.override_substitution(admin_id, target["id"], chosen["teacher_id"],
                                               reason, force=force)
                except (msvc.ManualError, PermissionError) as exc:
                    st.error(str(exc))
                else:
                    st.toast("Substitute changed.")
                    st.rerun()

    show_substitution_analytics(admin_id, version["id"])
    st.divider()
    with st.expander("Scoring weights (must total 100)"):
        current = svc._load_weights()
        with st.form("fs_weights"):
            vals = {k: st.number_input(k.replace("_", " ").title(), min_value=0, max_value=100,
                                       value=int(current[k]), key=f"fs_w_{k}") for k in CRITERIA}
            saved = st.form_submit_button("Save weights")
        if saved:
            try:
                svc.save_weights(admin_id, vals)
            except (ValueError, svc.SubstitutionError, PermissionError) as exc:
                st.error(str(exc))
            else:
                st.success("Weights saved.")
