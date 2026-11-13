#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/snapclass_root.sh" || exit 1
cd "$SNAPCLASS_ROOT" || exit 1
for need in src/ui/widgets.py src/services/attendance_stats.py; do
  [ -f "$need" ] || { echo "Missing $need. Run merge_1_base_layout.sh first."; exit 1; }
done

f="src/components/header.py"
cp "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"
cat > "$f" << 'PYEOF'
import streamlit as st

LOGO_URL = "https://i.ibb.co/YTYGn5qV/logo.png"


def header_home():
    st.markdown(f"""
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; margin-bottom:30px; margin-top:30px">
            <img src='{LOGO_URL}' alt='SnapClass logo' style='height:100px;' />
            <h1 style='text-align:center; color:#E0E3FF'>SNAP<br/>CLASS</h1>
        </div>
    """, unsafe_allow_html=True)


def header_dashboard():
    st.markdown(f"""
        <div style="display:flex; align-items:center; justify-content:center; gap:10px">
            <img src='{LOGO_URL}' alt='SnapClass logo' style='height:85px;' />
            <h2 style='text-align:left; color:#5865F2'>SNAP<br/>CLASS</h2>
        </div>
    """, unsafe_allow_html=True)
PYEOF

f="src/components/subject_card.py"
cp "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"
cat > "$f" << 'PYEOF'
import streamlit as st

from src.services.attendance_stats import status_for
from src.ui.widgets import chip, esc, progress_html


def subject_card(name, code, section, stats=None, footer_callback=None, course=None, year=None,
                 pct=None, total=None):
    """Same call as before. pct/total are optional: when given, the card also shows a status
    chip and a progress bar with a marker at 75%."""
    extra = ""
    if course:
        extra += f" | Course : {esc(course)}"
    if year:
        extra += f" | Year : {esc(year)}"

    status_html, bar_html = "", ""
    if pct is not None:
        count = 1 if total is None else total
        kind, label, icon = status_for(pct, count)
        status_html = chip(label, kind, icon)
        if kind == "none":
            bar_html = '<div class="sc-sub">No attendance recorded yet.</div>'
        else:
            bar_html = (progress_html(pct, total=count)
                        + f'<div class="sc-sub">{pct:.0f}% attendance. The line marks 75%.</div>')

    stats_html = ""
    if stats:
        items = "".join(
            f'<div style="background:#EB459E10; padding:5px 12px; border-radius:12px; font-size:0.9rem">'
            f'{esc(icon)} <b>{esc(value)}</b> {esc(label)} </div>'
            for icon, label, value in stats
        )
        stats_html = f'<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">{items}</div>'

    html = (
        '<div style="background:white; border-left:8px solid #EB459E; padding:25px; border-radius:20px; '
        'border:1px solid black; margin-bottom:20px;">'
        f'<div class="sc-row"><h3 style="margin:0; color:#1e293b; font-size:1.5rem">{esc(name)}</h3>{status_html}</div>'
        f'<p style="color:#64748b; margin:10px 0;">Code : <span style="background:#E0E3FF; color:#5865F2; '
        f'padding:2px 8px; border-radius:5px;">{esc(code)} </span> | Section : {esc(section)}{extra}</p>'
        f'{bar_html}{stats_html}</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    if footer_callback:
        footer_callback()
PYEOF

python3 -m py_compile src/components/header.py src/components/subject_card.py && echo "compiled both"
git diff --stat -- src/components/header.py src/components/subject_card.py
