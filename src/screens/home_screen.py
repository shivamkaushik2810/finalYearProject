import streamlit as st
from src.components.header import header_home
from src.components.footer import footer_home
from src.ui.base_layout import style_base_layout, style_background_home
from src.ui.home_fix import inject_home_fix


def home_screen():

    header_home()
    style_background_home()
    style_base_layout()
    inject_home_fix()

    col1, col2, col3 = st.columns(3, gap="large")

    with col1:
        st.header("I'm Student")
        st.image("https://i.ibb.co/844D9Lrt/mascot-student.png", width=120)
        if st.button('Student Portal', type='primary', icon=':material/arrow_outward:', icon_position='right'):
            st.session_state['login_type'] = 'student'
            st.rerun()

    with col2:
        st.header("I'm Teacher")
        st.image("https://i.ibb.co/CsmQQV6X/mascot-prof.png", width=145)
        if st.button('Teacher Portal', type='primary', icon=':material/arrow_outward:', icon_position='right'):
            st.session_state['login_type'] = 'teacher'
            st.rerun()

    with col3:
        st.header("I'm Parent")
        st.markdown("<div style='font-size:96px;line-height:120px;'>👨‍👩‍👧</div>", unsafe_allow_html=True)
        if st.button('Parent Portal', type='primary', icon=':material/arrow_outward:', icon_position='right'):
            st.session_state['login_type'] = 'parent'
            st.rerun()

    # The admin link is not shown here. Admins use the private route (ADMIN_ROUTE_KEY).

    # Admin entry for testing. Hide before deployment: SHOW_ADMIN_LINK = false in secrets.
    try:
        _show_admin = st.secrets.get("SHOW_ADMIN_LINK", True)
    except Exception:
        _show_admin = True
    if str(_show_admin).lower() not in ("false", "0", "no"):
        st.markdown("<style>.st-key-home_admin{max-width:260px;margin:24px auto 0 auto;}"
                    ".st-key-home_admin button{width:100%;}</style>", unsafe_allow_html=True)
        with st.container(key="home_admin"):
            if st.button("Admin login", type="secondary", icon=":material/admin_panel_settings:",
                         width="stretch", key="home_admin_btn"):
                st.session_state['login_type'] = 'admin'
                st.rerun()

    footer_home()
