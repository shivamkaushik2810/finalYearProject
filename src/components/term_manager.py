import re

import pandas as pd
import streamlit as st

from src.database.config import supabase

YEAR_RE = re.compile(r"^\d{4}-\d{2}$")


def _clean_year(v):
    v = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    return v or None


def _clean_sem(v):
    if v is None or pd.isna(v):
        return None
    return int(v)


def admin_term_manager():
    if not st.session_state.get("admin_data"):
        return
    st.subheader("📅 Academic Terms")
    st.caption("Give each subject an academic year (for example 2026-27) and a semester. "
               "These power the filters in Student Analytics.")
    try:
        rows = (supabase.table("subjects")
                .select("subject_id, name, subject_code, section, academic_year, semester, teachers(name)")
                .order("name").execute().data or [])
    except Exception as e:
        print(f"Terms: {type(e).__name__}")
        st.error("Academic terms are not set up yet. Run the academic terms SQL in Supabase.")
        return
    if not rows:
        st.info("No subjects yet.")
        return

    df = pd.DataFrame([{
        "subject_id": r["subject_id"], "Subject": r["name"], "Code": r["subject_code"], "Section": r.get("section") or "",
        "Teacher": (r.get("teachers") or {}).get("name", ""),
        "Academic year": r.get("academic_year") or "", "Semester": r.get("semester"),
    } for r in rows])

    with st.expander("Bulk assign to subjects that have no value yet"):
        b1, b2 = st.columns(2)
        year = b1.text_input("Academic year", placeholder="2026-27", key="term_bulk_year").strip()
        sem = b2.number_input("Semester", 1, 12, 1, key="term_bulk_sem")
        if st.button("Apply to unassigned subjects", key="term_bulk_btn"):
            if not YEAR_RE.match(year):
                st.error("Use the format 2026-27.")
            else:
                supabase.table("subjects").update({"academic_year": year}).is_("academic_year", "null").execute()
                supabase.table("subjects").update({"semester": int(sem)}).is_("semester", "null").execute()
                st.cache_data.clear()
                st.toast("Applied.")
                st.rerun()

    edited = st.data_editor(
        df, hide_index=True, key="term_editor", disabled=["Subject", "Code", "Section", "Teacher"],
        column_config={"subject_id": None,
                       "Academic year": st.column_config.TextColumn("Academic year", help="Format 2026-27"),
                       "Semester": st.column_config.NumberColumn("Semester", min_value=1, max_value=12, step=1)})

    if st.button("Save changes", type="primary", key="term_save"):
        saved, errors = 0, []
        for old, new in zip(df.to_dict("records"), edited.to_dict("records")):
            y_old, y_new = _clean_year(old["Academic year"]), _clean_year(new["Academic year"])
            s_old, s_new = _clean_sem(old["Semester"]), _clean_sem(new["Semester"])
            if (y_old, s_old) == (y_new, s_new):
                continue
            if y_new and not YEAR_RE.match(y_new):
                errors.append(f"{new['Subject']}: academic year must look like 2026-27")
                continue
            if s_new is not None and not 1 <= s_new <= 12:
                errors.append(f"{new['Subject']}: semester must be 1 to 12")
                continue
            sid = new["subject_id"].item() if hasattr(new["subject_id"], "item") else new["subject_id"]
            supabase.table("subjects").update({"academic_year": y_new, "semester": s_new}).eq("subject_id", sid).execute()
            saved += 1
        for e in errors:
            st.error(e)
        if saved:
            st.cache_data.clear()
            st.toast(f"Saved {saved} subject(s).")
            st.rerun()
