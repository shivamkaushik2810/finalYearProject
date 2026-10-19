import streamlit as st
from src.components.header import header_home
from src.components.footer import footer_home
from src.ui.base_layout import style_base_layout, style_background_home


def home_screen():

    header_home()
    style_background_home()
    style_base_layout()

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

    st.markdown("<div style='text-align:center;margin-top:10px;'>"
                "<a href='?admin=1' target='_self' style='color:#E0E3FF;font-size:13px;'>Admin login</a></div>",
                unsafe_allow_html=True)

    footer_home()
