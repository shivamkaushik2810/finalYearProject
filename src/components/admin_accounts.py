import streamlit as st

from src.services import admin_service as svc
from src.ui.widgets import confirm_dialog

STATUS_LABEL = {"pending": "Pending approval", "approved": "Active", "rejected": "Deactivated"}


def _run(fn, arg, ok_msg):
    try:
        fn(arg)
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        print(f"accounts action failed: {type(e).__name__}")
        st.error("That did not work. Try again.")
        return
    st.toast(ok_msg)
    st.rerun()


def admin_accounts_panel():
    st.subheader("👩‍🏫 Teacher accounts")
    st.caption("Unlock accounts locked after failed logins, or deactivate a teacher. A deactivated teacher "
               "cannot log in again. A teacher who is already logged in stays in until they log out.")
    try:
        teachers = svc.list_teachers()
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        print(f"accounts load failed: {type(e).__name__}")
        st.error("Could not load teacher accounts.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Active", sum(1 for t in teachers if t.get("status") == "approved"))
    c2.metric("Locked now", sum(1 for t in teachers if t.get("locked_until")))
    c3.metric("Deactivated", sum(1 for t in teachers if t.get("status") == "rejected"))

    search = st.text_input("Search by name or username", key="acc_search").strip().lower()
    shown = [t for t in teachers
             if not search or search in (t.get("name") or "").lower()
             or search in (t.get("username") or "").lower()]
    if not shown:
        st.info("No teachers match.")
        return

    for t in shown:
        tid = t["teacher_id"]
        name = t.get("name") or "Unknown"
        status = t.get("status") or ""
        with st.container(border=True):
            a, b = st.columns([4, 2], vertical_alignment="center")
            with a:
                st.write(f"**{name}** (@{t.get('username') or '-'})")
                flag = " · 🔒 locked" if t.get("locked_until") else ""
                st.caption(f"{STATUS_LABEL.get(status, status)} · failed logins: "
                           f"{t.get('failed_attempts') or 0}{flag}")
            with b:
                if t.get("locked_until") and st.button("Unlock", key=f"acc_unlock_{tid}", width="stretch"):
                    _run(svc.unlock_teacher, tid, f"{name} unlocked.")
                if status == "approved":
                    if st.button("Deactivate", key=f"acc_deact_{tid}", width="stretch"):
                        def _do(tid=tid, name=name):
                            _run(svc.deactivate_teacher, tid, f"{name} deactivated.")
                        confirm_dialog(f"Deactivate {name}? They will not be able to log in until "
                                       "you reactivate the account.", "Deactivate", _do,
                                       key=f"deact_{tid}")
                elif status == "rejected":
                    if st.button("Reactivate", key=f"acc_react_{tid}", type="primary", width="stretch"):
                        _run(svc.reactivate_teacher, tid, f"{name} reactivated.")
