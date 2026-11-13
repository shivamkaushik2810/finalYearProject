import streamlit as st

_ROOT = """
:root{--sc-primary:#5865F2;--sc-primary-dark:#3C3489;--sc-accent:#EB459E;--sc-bg:#E0E3FF;
--sc-surface:#FFFFFF;--sc-text:#1e293b;--sc-muted:#475569;--sc-border:#cbd5e1;
--sc-good:#3B6D11;--sc-good-bg:#EAF3DE;--sc-avg:#854F0B;--sc-avg-bg:#FAEEDA;
--sc-bad:#A32D2D;--sc-bad-bg:#FCEBEB;--sc-radius:14px;--sc-radius-pill:999px;}
"""

_BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Climate+Crisis:YEAR@1979&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap');

/* hide Streamlit chrome, but keep the header so the mobile menu button still works */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

.block-container { padding-top: 1.5rem !important; }

h1 { font-family: 'Climate Crisis', sans-serif !important; font-size: 3.5rem !important;
     line-height: 1.1 !important; margin-bottom: 0 !important; }
h2 { font-family: 'Climate Crisis', sans-serif !important; font-size: 2rem !important;
     line-height: 0.9 !important; margin-bottom: 0 !important; }
h3, h4, p, label { font-family: 'Outfit', sans-serif; }
.stApp { color: var(--sc-text); }

/* buttons: primary = filled, secondary = outline, tertiary = quiet, danger = red */
button[data-testid^="stBaseButton-primary"], button[kind="primary"] {
  background: var(--sc-primary) !important; color: #fff !important;
  border: 1px solid var(--sc-primary) !important; border-radius: var(--sc-radius-pill) !important;
  padding: 10px 20px !important; transition: transform .2s ease-in-out !important; }
button[data-testid^="stBaseButton-secondary"], button[kind="secondary"] {
  background: transparent !important; color: var(--sc-primary-dark) !important;
  border: 1px solid var(--sc-primary) !important; border-radius: var(--sc-radius-pill) !important;
  padding: 10px 20px !important; transition: transform .2s ease-in-out !important; }
button[data-testid^="stBaseButton-tertiary"], button[kind="tertiary"] {
  background: transparent !important; color: var(--sc-text) !important;
  border: 1px solid transparent !important; border-radius: var(--sc-radius-pill) !important;
  padding: 10px 20px !important; }
button[data-testid^="stBaseButton-primary"]:hover, button[data-testid^="stBaseButton-secondary"]:hover,
button[kind="primary"]:hover, button[kind="secondary"]:hover { transform: scale(1.03); }
button[data-testid^="stBaseButton-tertiary"]:hover, button[kind="tertiary"]:hover {
  background: rgba(88,101,242,.12) !important; }

[class*="st-key-danger"] button {
  background: transparent !important; color: var(--sc-bad) !important;
  border: 1px solid var(--sc-bad) !important; }
[class*="st-key-danger"] button[data-testid^="stBaseButton-primary"],
[class*="st-key-danger"] button[kind="primary"] {
  background: var(--sc-bad) !important; color: #fff !important; }

/* section navigation (segmented control) */
[data-testid="stButtonGroup"] { flex-wrap: wrap; gap: 6px; }
button[data-testid^="stBaseButton-segmented_control"] {
  background: #fff !important; color: var(--sc-text) !important;
  border: 1px solid var(--sc-border) !important; border-radius: var(--sc-radius-pill) !important; }
button[data-testid="stBaseButton-segmented_controlActive"] {
  background: var(--sc-primary) !important; color: #fff !important; border-color: var(--sc-primary) !important; }

button:focus-visible, input:focus-visible, textarea:focus-visible {
  outline: 3px solid var(--sc-primary-dark) !important; outline-offset: 2px; }

/* components used by cards, stats, steppers and charts */
.sc-chip { display:inline-block; font-size:.75rem; font-weight:500; padding:2px 10px;
  border-radius:var(--sc-radius-pill); white-space:nowrap; }
.sc-good { background:var(--sc-good-bg); color:var(--sc-good); }
.sc-avg  { background:var(--sc-avg-bg);  color:var(--sc-avg); }
.sc-risk { background:var(--sc-bad-bg);  color:var(--sc-bad); }
.sc-none { background:#e2e8f0; color:var(--sc-muted); }
.sc-card { background:var(--sc-surface); border:1px solid var(--sc-border);
  border-radius:var(--sc-radius); padding:14px 16px; margin-bottom:12px; }
.sc-card h3 { margin:0; font-size:1.15rem; color:var(--sc-text); }
.sc-sub { color:var(--sc-muted); font-size:.85rem; margin:4px 0 0; }
.sc-row { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.sc-bar { position:relative; height:8px; background:#e2e8f0; border-radius:6px; margin:10px 0 4px; }
.sc-bar i { position:absolute; left:0; top:0; bottom:0; border-radius:6px; }
.sc-bar u { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--sc-muted); }
.sc-fill-good { background:var(--sc-good); } .sc-fill-avg { background:#BA7517; }
.sc-fill-risk { background:var(--sc-bad); }  .sc-fill-none { background:#94a3b8; }
.sc-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:6px 0 14px; }
.sc-stat { background:var(--sc-surface); border:1px solid var(--sc-border); border-radius:var(--sc-radius); padding:12px 14px; }
.sc-stat-l { font-size:.8rem; color:var(--sc-muted); }
.sc-stat-v { font-size:1.6rem; font-weight:500; line-height:1.3; }
.sc-tone-bad .sc-stat-v { color:var(--sc-bad); } .sc-tone-good .sc-stat-v { color:var(--sc-good); }
.sc-tone-avg .sc-stat-v { color:var(--sc-avg); }
.sc-empty { background:var(--sc-surface); border:1px dashed var(--sc-muted); border-radius:var(--sc-radius);
  padding:22px 16px; text-align:center; margin:8px 0 14px; }
.sc-empty b { font-size:1.05rem; } .sc-empty p { color:var(--sc-muted); margin:4px 0 0; }
.sc-steps { display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px; margin:6px 0 14px; font-size:.9rem; }
.sc-step b { display:inline-flex; width:24px; height:24px; border-radius:50%; align-items:center;
  justify-content:center; font-size:.75rem; margin-right:6px; font-weight:500; }
.sc-step.done b { background:var(--sc-good); color:#fff; }
.sc-step.cur b  { background:var(--sc-primary); color:#fff; }
.sc-step.todo b { background:#fff; color:var(--sc-muted); border:1px solid var(--sc-muted); }
.sc-step.cur { font-weight:500; } .sc-step.todo { color:var(--sc-muted); }
.sc-pw { display:flex; gap:4px; margin:4px 0; }
.sc-pw i { flex:1; height:5px; border-radius:3px; background:#cbd5e1; }
.sc-hm { display:grid; grid-template-columns:64px repeat(6,minmax(0,1fr)); gap:4px; font-size:.8rem; align-items:center; }
.sc-hm span.c { text-align:center; border-radius:6px; padding:4px 0; }

@media (max-width: 640px) {
  h1 { font-size: 2.2rem !important; } h2 { font-size: 1.5rem !important; }
  .block-container { padding: 1rem .75rem !important; }
  button { min-height: 44px; }
  .sc-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: reduce) { button { transition: none !important; } }
"""


def _inject(extra=""):
    st.markdown("<style>" + _ROOT + _BASE_CSS + extra + "</style>", unsafe_allow_html=True)


def style_background_home():
    _inject("""
    .stApp { background: #5865F2 !important; }
    .stApp div[data-testid="stColumn"] { background-color:#E0E3FF !important;
        padding:2.5rem !important; border-radius:5rem !important; }
    @media (max-width: 640px) {
      .stApp div[data-testid="stColumn"] { padding:1.25rem !important; border-radius:1.75rem !important; }
    }
    """)


def style_background_dashboard():
    _inject(".stApp { background: #E0E3FF !important; }")


def style_base_layout():
    _inject()
