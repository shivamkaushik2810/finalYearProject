import streamlit as st
from src.services.feedback_service import (
    CATEGORIES, MAX_LEN, ALREADY_MSG, is_feedback_enabled, set_feedback_enabled,
    submit_feedback, list_feedback_meta, read_and_delete_feedback,
    has_sent_today, today_ist
)
from src.utils.time_utils import to_ist

POLL_SECONDS = 5


@st.fragment(run_every=POLL_SECONDS)
def _feedback_form_fragment(role, user_id, user_name):
    # Re-runs every few seconds so the form appears/disappears when the
    # admin flips the switch, without a page refresh.
    if not is_feedback_enabled():
        return

    day = today_ist()
    sent_flag = f"fb_sent_{role}_{user_id}_{day}"
    sent = bool(st.session_state.get(sent_flag)) or has_sent_today(role, str(user_id), day)

    with st.expander("💬 Send Feedback"):
        key = f"fb_{role}"
        if sent:
            st.info("✅ You have already sent feedback today. "
                    "You can send again tomorrow.")
        category = st.selectbox("Category", CATEGORIES, key=f"{key}_cat", disabled=sent)
        message = st.text_area(
            "Your feedback", max_chars=MAX_LEN, key=f"{key}_msg", disabled=sent,
            placeholder="Tell the admin what's working or what could be better..."
        )
        if st.button("Send Feedback", type="primary", key=f"{key}_btn", disabled=sent):
            ok, msg = submit_feedback(role, user_id, user_name, category, message)
            if ok or msg == ALREADY_MSG:
                st.session_state[sent_flag] = True
                st.rerun(scope="fragment")
            else:
                st.error(msg)


def show_feedback_section(role, user_id, user_name):
    """Student/teacher form. Renders nothing unless admin enabled feedback."""
    _feedback_form_fragment(role, user_id, user_name)


def _fmt(ts):
    try:
        return to_ist(ts).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return ts or "Unknown"


@st.fragment(run_every=POLL_SECONDS)
def _admin_panel_fragment():
    st.subheader("💬 Feedback")

    enabled = is_feedback_enabled()
    new_val = st.toggle("Enable feedback for students and teachers", value=enabled)
    if new_val != enabled:
        try:
            set_feedback_enabled(new_val)
            st.rerun(scope="fragment")
        except Exception as e:
            st.error(f"Could not change setting: {type(e).__name__}")
            return

    st.caption("Reading a message deletes it permanently from the database. "
               f"This list refreshes every {POLL_SECONDS} seconds.")
    st.divider()

    opened = st.session_state.setdefault("fb_opened", [])
    for i, row in enumerate(list(opened)):
        with st.container(border=True):
            st.write(f"**{row['sender_role'].title()}: {row.get('sender_name') or 'Unknown'}** "
                     f"· {row['category']} · {_fmt(row['created_at'])}")
            st.write(row["message"])
            if st.button("Dismiss", key=f"fb_dismiss_{row['id']}"):
                opened.pop(i)
                st.rerun(scope="fragment")

    try:
        items = list_feedback_meta()
    except Exception as e:
        st.error(f"Could not load feedback: {type(e).__name__}")
        return

    st.write(f"**Unread: {len(items)}**")
    if not items:
        st.info("No feedback waiting.")
        return

    for it in items:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            with c1:
                st.write(f"**{it['sender_role'].title()}: {it.get('sender_name') or 'Unknown'}** "
                         f"· {it['category']} · {_fmt(it['created_at'])}")
            with c2:
                if st.button("Read & delete", key=f"fb_read_{it['id']}"):
                    row = read_and_delete_feedback(it["id"])
                    if row:
                        opened.append(row)
                    else:
                        st.warning("Already read by another session.")
                    st.rerun(scope="fragment")


def show_admin_feedback_panel():
    """Call ONLY from inside the authenticated admin area."""
    _admin_panel_fragment()
