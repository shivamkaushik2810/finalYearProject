import streamlit as st

from src.services import admin_service as svc


def admin_system_panel():
    st.subheader("🩺 System health")
    try:
        quota = svc.email_quota_today()
        pending = len(svc.list_teachers("pending"))
        approved = len(svc.list_teachers("approved"))
        locked = len(svc.locked_teachers())
    except PermissionError:
        st.error("Administrator access required.")
        return
    except Exception as e:
        print(f"health load failed: {type(e).__name__}")
        st.warning("Some health figures could not be loaded. Check that sql/reserve_email_quota.sql "
                   "has been run in Supabase.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Email sent today", quota["sent"])
    c2.metric("Email quota left", quota["remaining"])
    c3.metric("Teachers waiting approval", pending)
    c4.metric("Accounts locked", locked)
    frac = min(1.0, quota["sent"] / quota["limit"]) if quota["limit"] else 0.0
    st.progress(frac, text=f"Daily email use: {quota['sent']} of {quota['limit']}")
    st.caption(f"{approved} active teacher account(s). Email jobs run in memory, so a job that is still "
               "running is only visible on the attendance screen that started it.")
