"""Teacher portal look: sidebar brand and a neutral theme that matches the admin portal.
Pure helpers and CSS only. No data access."""
import html

import streamlit as st

TEACHER_CSS = """
:root{--sc-primary:#4F46E5;--sc-primary-dark:#3730A3;--sc-bg:#F3F5F9;--sc-surface:#FFFFFF;
--sc-text:#0F172A;--sc-muted:#64748B;--sc-border:#E2E8F0;}
.stApp{background:#F3F5F9!important;}
.block-container{max-width:1280px;padding-top:1.5rem!important;padding-bottom:3rem!important;}
h1,h2,h3,h4{font-family:'Outfit',sans-serif!important;color:#0F172A!important;letter-spacing:-0.01em;}
h2{font-size:1.4rem!important;font-weight:600!important;}
h3{font-size:1.05rem!important;font-weight:600!important;}

section[data-testid="stSidebar"]{background:#0B1220!important;}
section[data-testid="stSidebar"] > div{padding-top:1.25rem;}
section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label{color:#94A3B8;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label{padding:.5rem .75rem;border-radius:8px;margin:2px 0;width:100%;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover{background:#1E293B;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked){background:#1E293B;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p{color:#FFFFFF!important;font-weight:600;}
section[data-testid="stSidebar"] hr{border-color:#1E293B!important;}
.tp-brand{display:flex;align-items:center;gap:10px;margin:0 0 1rem 0;}
.tp-mark{width:36px;height:36px;border-radius:9px;background:#4F46E5;color:#FFFFFF;display:flex;align-items:center;justify-content:center;font-weight:700;flex:none;}
.tp-name{color:#FFFFFF;font-weight:650;font-size:1rem;line-height:1.1;}
.tp-sub{color:#94A3B8;font-size:.78rem;}

div[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF;border-radius:12px!important;border:1px solid #E2E8F0!important;box-shadow:0 1px 2px rgba(15,23,42,.04);}
div[data-testid="stMetric"]{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04);}
div[data-testid="stMetricLabel"] p{color:#64748B!important;font-size:.82rem!important;font-weight:500!important;}
div[data-testid="stDataFrame"]{border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;}
button[kind="primary"]{background:#4F46E5!important;border:1px solid #4F46E5!important;color:#FFFFFF!important;border-radius:8px!important;font-weight:600!important;}
button[kind="primary"]:hover{background:#3730A3!important;border-color:#3730A3!important;}
button[kind="secondary"]{border-radius:8px!important;}
div[data-baseweb="input"] > div,div[data-baseweb="select"] > div,textarea{border-radius:8px!important;}
@media (max-width:640px){.block-container{padding:1rem .75rem!important;}}
"""


def inject_teacher_theme():
    st.markdown("<style>" + TEACHER_CSS + "</style>", unsafe_allow_html=True)


def teacher_brand_html():
    return (
        '<div class="tp-brand"><div class="tp-mark">S</div><div>'
        '<div class="tp-name">SnapClass</div>'
        '<div class="tp-sub">Teacher portal</div>'
        '</div></div>'
    )


def _esc(v):
    return html.escape("" if v is None else str(v), quote=True)
