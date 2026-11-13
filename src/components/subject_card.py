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
