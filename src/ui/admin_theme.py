"""Admin portal look: navigation, page headers and a neutral professional theme.
Pure helpers (no database access). The HTML builders are unit-tested."""
import html

import streamlit as st

# key, sidebar label, page title, page description
ADMIN_PAGES = [
    ("overview", "Overview and reports", "Overview",
     "Attendance across every subject, section and course."),
    ("approvals", "Teacher approvals", "Teacher approvals",
     "Review new teacher sign-ups and see who is active."),
    ("accounts", "Teacher accounts", "Teacher accounts",
     "Unlock locked accounts or deactivate access."),
    ("timetable", "Timetable", "Timetable",
     "Schedule classes and check for clashes."),
    ("terms", "Academic terms", "Academic terms",
     "Set the academic year and semester for each subject."),
    ("students", "Student analytics", "Student analytics",
     "Drill into one student's attendance and marks."),
    ("sections", "Section analytics", "Section analytics",
     "Compare sections and find defaulters."),
    ("sessions", "Teacher sessions", "Teacher sessions",
     "Every attendance session taken, by teacher and section."),
    ("defaulters", "Defaulter emails", "Defaulter emails",
     "Send attendance alerts to parents."),
    ("feedback", "Feedback", "Feedback",
     "Messages from students and teachers."),
    ("audit", "Corrections audit", "Corrections audit",
     "Every attendance change, with who made it and why."),
    ("system", "System health", "System health",
     "Email quota, approvals waiting and locked accounts."),
]

ADMIN_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300..700&display=swap');
:root{--ad-bg:#F3F5F9;--ad-surface:#FFFFFF;--ad-ink:#0F172A;--ad-muted:#64748B;--ad-line:#E2E8F0;
--ad-brand:#4F46E5;--ad-brand-ink:#3730A3;--ad-side:#0B1220;--ad-side-ink:#94A3B8;--ad-side-active:#1E293B;}
.stApp{background:var(--ad-bg)!important;}
.block-container{max-width:1280px;padding-top:1.5rem!important;padding-bottom:3rem!important;}
html,body,.stApp,.stMarkdown,p,label,button,input,textarea{font-family:'Outfit',sans-serif;}
h1,h2,h3,h4{font-family:'Outfit',sans-serif!important;color:var(--ad-ink)!important;line-height:1.3!important;letter-spacing:-0.01em;}
h1{font-size:1.75rem!important;font-weight:650!important;}
h2{font-size:1.3rem!important;font-weight:600!important;}
h3{font-size:1.05rem!important;font-weight:600!important;}

section[data-testid="stSidebar"]{background:var(--ad-side)!important;}
section[data-testid="stSidebar"] > div{padding-top:1.25rem;}
section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] span{color:var(--ad-side-ink);}
section[data-testid="stSidebar"] hr{border-color:#1E293B!important;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label{padding:.5rem .75rem;border-radius:8px;margin:2px 0;width:100%;}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover{background:var(--ad-side-active);}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked){background:var(--ad-side-active);}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p{color:#FFFFFF!important;font-weight:600;}
section[data-testid="stSidebar"] .ad-brand-name{color:#FFFFFF!important;font-weight:650;font-size:1rem;line-height:1.1;}
section[data-testid="stSidebar"] .ad-brand-sub{color:var(--ad-side-ink)!important;font-size:.78rem;}
.ad-brand{display:flex;align-items:center;gap:10px;margin:0 0 1rem 0;}
.ad-mark{width:36px;height:36px;border-radius:9px;background:var(--ad-brand);color:#FFFFFF;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1rem;flex:none;}
.ad-brand-name{color:var(--ad-ink);font-weight:650;font-size:1rem;line-height:1.1;}
.ad-brand-sub{color:var(--ad-muted);font-size:.78rem;}

div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--ad-surface);border-radius:12px!important;border:1px solid var(--ad-line)!important;box-shadow:0 1px 2px rgba(15,23,42,.04);}
div[data-testid="stMetric"]{background:var(--ad-surface);border:1px solid var(--ad-line);border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04);}
div[data-testid="stMetricLabel"] p{color:var(--ad-muted)!important;font-size:.82rem!important;font-weight:500!important;}
div[data-testid="stMetricValue"]{color:var(--ad-ink);font-weight:650;}
div[data-testid="stDataFrame"]{border:1px solid var(--ad-line);border-radius:10px;overflow:hidden;}

button[kind="primary"]{background:var(--ad-brand)!important;border:1px solid var(--ad-brand)!important;border-radius:8px!important;color:#FFFFFF!important;font-weight:600!important;}
button[kind="primary"]:hover{background:var(--ad-brand-ink)!important;border-color:var(--ad-brand-ink)!important;}
button[kind="secondary"]{background:#FFFFFF!important;border:1px solid #CBD5E1!important;border-radius:8px!important;color:var(--ad-ink)!important;}
button[kind="tertiary"]{border-radius:8px!important;}
div[data-baseweb="input"] > div,div[data-baseweb="select"] > div,textarea{border-radius:8px!important;background:#FFFFFF!important;}

.ad-topbar{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;padding:0 0 16px 0;margin-bottom:20px;border-bottom:1px solid var(--ad-line);}
.ad-eyebrow{font-size:.74rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ad-brand);}
.ad-title{font-size:1.75rem;font-weight:650;color:var(--ad-ink);line-height:1.2;margin-top:2px;}
.ad-sub{color:var(--ad-muted);font-size:.95rem;margin-top:4px;}
.ad-user{text-align:right;font-size:.82rem;color:var(--ad-muted);}
.ad-user b{display:block;color:var(--ad-ink);font-size:.95rem;}
.ad-login-title{font-size:1.4rem;font-weight:650;color:var(--ad-ink);margin:12px 0 2px;}
.ad-login-sub{color:var(--ad-muted);font-size:.92rem;margin-bottom:14px;}
@media (max-width:640px){.ad-topbar{flex-direction:column;align-items:flex-start;}.ad-user{text-align:left;}}
"""


def inject_admin_theme():
    st.markdown("<style>" + ADMIN_CSS + "</style>", unsafe_allow_html=True)


def _esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def header_html(title, subtitle, admin_name):
    return (
        '<div class="ad-topbar"><div>'
        '<div class="ad-eyebrow">Administration</div>'
        f'<div class="ad-title">{_esc(title)}</div>'
        f'<div class="ad-sub">{_esc(subtitle)}</div>'
        '</div>'
        f'<div class="ad-user">Signed in as<b>{_esc(admin_name)}</b></div>'
        '</div>'
    )


def brand_html(caption):
    return (
        '<div class="ad-brand"><div class="ad-mark">S</div><div>'
        '<div class="ad-brand-name">SnapClass</div>'
        f'<div class="ad-brand-sub">{_esc(caption)}</div>'
        '</div></div>'
    )


def page_header(title, subtitle, admin_name):
    st.markdown(header_html(title, subtitle, admin_name), unsafe_allow_html=True)


def sidebar_brand(admin_name):
    st.markdown(brand_html(f"Admin console"), unsafe_allow_html=True)


def login_brand():
    st.markdown(brand_html("Administrator sign in"), unsafe_allow_html=True)
