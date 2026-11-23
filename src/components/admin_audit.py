import pandas as pd
import streamlit as st

from src.services import admin_service as svc
from src.services.pure_logic import csv_safe


def _state(v):
    return "Present" if v else "Absent"


def admin_audit_panel():
    st.subheader("🧾 Attendance correction audit")
    st.caption("Every change a teacher made to an attendance record. Read-only: the database does not allow "
               "edits or deletes to this log.")
    try:
        rows = svc.list_corrections()
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        print(f"audit load failed: {type(e).__name__}")
        st.error("Could not load the audit log.")
        return
    if not rows:
        st.info("No corrections recorded yet.")
        return

    df = pd.DataFrame([{
        "When": str(r.get("changed_at") or "")[:16].replace("T", " "),
        "Teacher ID": str(r.get("changed_by") or ""),
        "Subject ID": str(r.get("subject_id") or ""),
        "Student ID": str(r.get("student_id") or ""),
        "Old": _state(r.get("old_value")),
        "New": _state(r.get("new_value")),
        "Reason": r.get("reason") or "",
    } for r in rows])

    q = st.text_input("Filter by teacher ID, subject ID, student ID or reason",
                      key="aud_q").strip().lower()
    if q and not df.empty:
        mask = df.apply(lambda row: q in " ".join(str(v) for v in row.values).lower(), axis=1)
        df = df[mask]
    if df.empty:
        st.info("No records match this filter.")
        return

    st.dataframe(df, hide_index=True, width="stretch")
    safe = df.apply(lambda col: col.map(csv_safe))
    st.download_button("⬇️ Download audit (CSV)", safe.to_csv(index=False).encode("utf-8"),
                       file_name="corrections_audit.csv", mime="text/csv", key="aud_csv")
