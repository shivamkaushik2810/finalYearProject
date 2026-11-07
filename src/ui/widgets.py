import html
import logging

import streamlit as st

from src.services.attendance_stats import status_for

log = logging.getLogger(__name__)


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def chip(label, kind="none", icon=""):
    prefix = f"{esc(icon)} " if icon else ""
    return f'<span class="sc-chip sc-{kind}">{prefix}{esc(label)}</span>'


def chip_for(percent, total=1):
    kind, label, icon = status_for(percent, total)
    return chip(label, kind, icon)


def progress_html(percent, target=75, total=1):
    value = max(0.0, min(100.0, float(percent or 0)))
    kind = status_for(value, total)[0]
    return (f'<div class="sc-bar" role="img" aria-label="{value:.0f} percent, target {target} percent">'
            f'<i class="sc-fill-{kind}" style="width:{value}%"></i><u style="left:{target}%"></u></div>')


def stat_cards(items):
    """items: list of (label, value, tone) where tone is '', 'good', 'avg' or 'bad'."""
    cells = "".join(
        f'<div class="sc-stat sc-tone-{esc(tone)}"><div class="sc-stat-l">{esc(label)}</div>'
        f'<div class="sc-stat-v">{esc(value)}</div></div>'
        for label, value, tone in items
    )
    st.markdown(f'<div class="sc-stats">{cells}</div>', unsafe_allow_html=True)


def empty_state(title, body):
    st.markdown(f'<div class="sc-empty"><b>{esc(title)}</b><p>{esc(body)}</p></div>', unsafe_allow_html=True)


def stepper(labels, current):
    """current is 1-based."""
    parts = []
    for i, label in enumerate(labels, start=1):
        state = "done" if i < current else "cur" if i == current else "todo"
        mark = "\u2713" if state == "done" else str(i)
        parts.append(f'<span class="sc-step {state}"><b>{mark}</b>{esc(label)}</span>')
    st.markdown(f'<div class="sc-steps">{"".join(parts)}</div>', unsafe_allow_html=True)


def password_requirements(pw):
    """Return (checks, score, label). checks is a list of (ok, text)."""
    import re
    pw = pw or ""
    checks = [
        (8 <= len(pw) <= 16, "8 to 16 characters"),
        (bool(re.search(r"[A-Z]", pw)), "An uppercase letter"),
        (bool(re.search(r"[a-z]", pw)), "A lowercase letter"),
        (bool(re.search(r"[0-9]", pw)), "A number"),
        (bool(re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', pw)), "A special character"),
    ]
    score = sum(1 for ok, _ in checks if ok)
    label = "Strong" if score == 5 else "Fair" if score >= 3 else "Weak"
    return checks, score, label


def render_password_checklist(pw):
    if not pw:
        return
    checks, score, label = password_requirements(pw)
    color = {"Strong": "#3B6D11", "Fair": "#BA7517", "Weak": "#A32D2D"}[label]
    segs = "".join(f'<i style="background:{color if n < score else "#cbd5e1"}"></i>' for n in range(5))
    tick, cross = "\u2713", "\u2717"
    lines = "<br>".join(f"{tick if ok else cross} {esc(text)}" for ok, text in checks)
    st.markdown(
        f'<div class="sc-pw" role="img" aria-label="Password strength: {label}">{segs}</div>'
        f'<div style="font-size:.85rem"><b>{label}</b><br>{lines}</div>',
        unsafe_allow_html=True,
    )


@st.dialog("Please confirm")
def confirm_dialog(message, confirm_label, on_confirm, key):
    """Destructive confirmation. The confirm button key starts with 'danger' so it renders red."""
    st.write(message)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Keep as is", key=f"keep_{key}", width="stretch"):
            st.rerun()
    with c2:
        if st.button(confirm_label, key=f"danger_{key}", type="primary", width="stretch"):
            try:
                on_confirm()
            except Exception:
                log.exception("Confirmed action failed: %s", key)
                st.error("That didn't work. Try again in a moment.")
                return
            st.rerun()
