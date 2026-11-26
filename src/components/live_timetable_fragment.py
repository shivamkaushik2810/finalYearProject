"""Keeps a timetable on screen up to date without a page refresh.

A Streamlit fragment reruns only this block every few seconds. It reads a small fingerprint of
the LIVE version; the full grid is redrawn only when the fingerprint changes, so the page does
not flicker when nothing has changed."""
import hashlib
import time

import streamlit as st

from src.services import published_timetable as pt

REFRESH_SECONDS = 15
NOTE_SECONDS = 6


def _fingerprint(version_id):
    """Changes whenever a class in the live version is added, changed or removed."""
    entries = pt.published_entries(version_id)
    raw = "|".join(sorted(
        f"{e.id}:{e.section_code}:{e.weekday}:{e.period_no}:{e.block_len}:{e.kind}:"
        f"{e.subject_code}:{e.faculty_code}:{e.room}"
        for e in entries))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def live_timetable(key, draw):
    """Calls draw(version) to show the live timetable, and refreshes it every REFRESH_SECONDS.
    draw receives the live version dict and must draw the grid."""

    @st.fragment(run_every=REFRESH_SECONDS)
    def _block():
        version = pt.published_version()
        if not version:
            st.info("The timetable has not been published yet.")
            return
        fp = _fingerprint(version["id"])
        seen_key = f"live_fp_{key}"
        changed_key = f"live_changed_at_{key}"
        if st.session_state.get(seen_key) not in (None, fp):
            st.session_state[changed_key] = time.time()
        st.session_state[seen_key] = fp
        changed_at = st.session_state.get(changed_key)
        if changed_at and time.time() - changed_at < NOTE_SECONDS:
            st.toast("The timetable was just updated.")
        draw(version)

    _block()
