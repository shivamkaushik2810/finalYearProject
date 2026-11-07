import streamlit as st

from src.services.attendance_stats import status_for
from src.ui.widgets import chip, esc, progress_html


def subject_card(name, code, section, stats=None, footer_callback=None, pct=None, total=None):
    """pct/total are optional. When given, the card shows a status chip and a progress bar."""
    status_html, bar_html = "", ""
    if pct is not None:
        kind, label, icon = status_for(pct, 1 if total is None else total)
        status_html = chip(label, kind, icon)
        bar_html = (progress_html(pct, total=1 if total is None else total)
                    + f'<div class="sc-sub">{pct:.0f}% attendance. The line marks 75%.</div>'
                    if kind != "none" else '<div class="sc-sub">No attendance recorded yet.</div>')

    stats_html = ""
    if stats:
        items = "".join(
            f'<div style="background:#EB459E10;padding:5px 12px;border-radius:12px;font-size:.9rem">'
            f'{esc(icon)} <b>{esc(value)}</b> {esc(label)}</div>'
            for icon, label, value in stats
        )
        stats_html = f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">{items}</div>'

    st.markdown(
        f'<div class="sc-card" style="border-left:8px solid #EB459E">'
        f'<div class="sc-row"><h3>{esc(name)}</h3>{status_html}</div>'
        f'<p class="sc-sub">Code <span style="background:#E0E3FF;color:#3C3489;padding:1px 8px;border-radius:5px">'
        f'{esc(code)}</span> &nbsp;|&nbsp; Section {esc(section)}</p>'
        f'{bar_html}{stats_html}</div>',
        unsafe_allow_html=True,
    )
    if footer_callback:
        footer_callback()
