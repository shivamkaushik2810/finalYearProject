import importlib
import importlib.util
import threading
import streamlit as st

from src.screens.home_screen import home_screen
from src.components.dialog_auto_enroll import auto_enroll_dialog
from src.services.scheduler import check_and_send_weekly_reports
from src.pipelines.self_learning import auto_retrain_if_needed

PORTALS = ("student", "teacher", "parent", "admin")


@st.cache_resource
def _startup_jobs():
    def _job():
        try:
            retrained, msg = auto_retrain_if_needed()
            if retrained:
                print(f"Auto retrain: {msg}")
        except Exception as e:
            print(f"Auto retrain error: {e}")
    threading.Thread(target=_job, daemon=True).start()
    return True


def _open_portal(portal):
    """portal 'x' -> src/screens/x_screen.py (function x_screen / x_portal / show_x_portal)."""
    module_name = f"src.screens.{portal}_screen"
    if importlib.util.find_spec(module_name) is None:
        st.error(f"Portal '{portal}' not found: {module_name}.py is missing.")
        return
    module = importlib.import_module(module_name)
    for name in (f"{portal}_screen", f"{portal}_portal", f"show_{portal}_portal", f"{portal}_dashboard"):
        fn = getattr(module, name, None)
        if callable(fn):
            fn()
            return
    funcs = [n for n in dir(module) if callable(getattr(module, n)) and not n.startswith("_")]
    st.error(f"No entry function in {module_name}.py. Found: {funcs}")


def _consume_portal_params():
    """?admin=1 / ?parent=1 / ... opens that portal once, then the param is removed."""
    if st.session_state.get("is_logged_in"):
        return
    for portal in PORTALS:
        if str(st.query_params.get(portal, "")).lower() in ("1", "true", "yes"):
            st.session_state["login_type"] = portal
            try:
                del st.query_params[portal]
            except Exception:
                pass
            return


def _enforce_role_lock():
    """A logged-in user can only ever open their own portal."""
    role = st.session_state.get("user_role")
    if (st.session_state.get("is_logged_in") and role in PORTALS
            and st.session_state.get("login_type") not in (None, role)):
        st.session_state["login_type"] = role


def main():
    st.set_page_config(
        page_title="SnapClass - Making Attendance faster using AI",
        page_icon="https://i.ibb.co/YTYGn5qV/logo.png",
    )

    _startup_jobs()
    check_and_send_weekly_reports()

    st.session_state.setdefault("login_type", None)

    _consume_portal_params()

    join_code = st.query_params.get("join-code")
    if join_code and st.session_state.login_type is None:
        st.session_state.login_type = "student"

    _enforce_role_lock()

    portal = st.session_state["login_type"]
    if portal in PORTALS:
        _open_portal(portal)
    else:
        home_screen()

    if (join_code and st.session_state.get("is_logged_in")
            and st.session_state.get("user_role") == "student"):
        auto_enroll_dialog(join_code)


main()
