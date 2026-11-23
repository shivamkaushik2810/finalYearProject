import streamlit as st

from src.database import analytics_db as adb
from src.services import section_export as sx


def admin_exports_panel():
    st.caption("The export contains student names and roll numbers. Download it only to a device you trust.")
    try:
        sections = adb.get_sections()
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        print(f"export sections failed: {type(e).__name__}")
        st.error("Could not load sections.")
        return
    if not sections:
        st.info("No sections yet.")
        return

    key = st.selectbox("Section", sorted(sections), key="exp_section",
                       format_func=lambda k: f"Section {k} ({sections[k]['count']} students)")
    if st.button("Build export", type="primary", key="exp_build"):
        try:
            with st.spinner("Building the export..."):
                data, filename, info = sx.build_section_export(key)
        except PermissionError:
            st.error("Administrator access required.")
            return
        except Exception as e:
            print(f"export failed: {type(e).__name__}")
            st.error("The export failed. Try again.")
            return
        st.session_state["exp_ready"] = (key, data, filename)
        st.success(f"Ready: {info['students']} students, {info['attendance_rows']} attendance rows.")

    ready = st.session_state.get("exp_ready")
    if ready and ready[0] == key:
        st.download_button("Download ZIP", ready[1], file_name=ready[2],
                           mime="application/zip", key="exp_dl")
