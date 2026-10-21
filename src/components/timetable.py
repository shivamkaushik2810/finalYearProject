from datetime import time as dtime
import streamlit as st
from src.database.config import supabase

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hhmm(t):
    return str(t)[:5]


# ───────────────────────── student / parent view ─────────────────────────

def render_timetable(student_id):
    st.subheader("🗓️ Weekly Timetable")
    try:
        subs = supabase.table('subject_students').select('subject_id').eq('student_id', student_id).execute().data or []
        ids = [s['subject_id'] for s in subs]
        if not ids:
            st.info("Not enrolled in any subject yet.")
            return
        rows = supabase.table('timetables').select('*, subjects(name, subject_code)')\
            .in_('subject_id', ids).order('day_of_week').order('start_time').execute().data or []
    except Exception as e:
        st.info("Timetable is not available right now.")
        print(f"Timetable error: {e}")
        return

    if not rows:
        st.info("No timetable has been published yet.")
        return

    by_day = {}
    for r in rows:
        by_day.setdefault(r['day_of_week'], []).append(r)
    for d in sorted(by_day):
        with st.container(border=True):
            st.write(f"**{DAYS[d]}**")
            for r in by_day[d]:
                sub = r.get('subjects') or {}
                room = f" · Room {r['room']}" if r.get('room') else ""
                st.write(f"🕐 {_hhmm(r['start_time'])}–{_hhmm(r['end_time'])} — "
                         f"{sub.get('name', '')} ({sub.get('subject_code', '')}){room}")


# ───────────────────────── admin management ─────────────────────────

def _find_clash(slots, subject, day, start, end, room, enrolled_cache):
    def enrolled(sid):
        if sid not in enrolled_cache:
            res = supabase.table('subject_students').select('student_id').eq('subject_id', sid).execute()
            enrolled_cache[sid] = {r['student_id'] for r in (res.data or [])}
        return enrolled_cache[sid]

    for o in slots:
        if o['day_of_week'] != day:
            continue
        o_start, o_end = str(o['start_time'])[:8], str(o['end_time'])[:8]
        if not (start < o_end and o_start < end):
            continue
        osub = o.get('subjects') or {}
        label = f"{osub.get('name', '?')} ({o_start[:5]}–{o_end[:5]})"
        if osub.get('teacher_id') == subject['teacher_id']:
            return f"This teacher already has a class then: {label}"
        if room.strip() and (o.get('room') or '').strip().lower() == room.strip().lower():
            return f"Room {room} is already booked then: {label}"
        common = enrolled(subject['subject_id']) & enrolled(o['subject_id'])
        if common:
            return f"{len(common)} student(s) are enrolled in both subjects, which clash with {label}"
    return None


def _opt_label(s):
    return (f"{s['name']} ({s['subject_code']}) — {s.get('course') or '-'} Y{s.get('year') or '-'} "
            f"Sec {s.get('section') or '-'} — {(s.get('teachers') or {}).get('name', '?')}")


def admin_timetable_manager():
    from src.components.filters import cascade_filter, fetch_all
    st.subheader("🗓️ Timetable Management")
    try:
        subjects = fetch_all(lambda: supabase.table('subjects')
                             .select('subject_id, name, subject_code, section, course, year, teacher_id, teachers(name)')
                             .order('subject_id'))
        slots = fetch_all(lambda: supabase.table('timetables')
                          .select('*, subjects(name, subject_code, section, course, year, teacher_id)')
                          .order('day_of_week').order('start_time').order('id'))
    except Exception as e:
        st.error("Timetable table is not available. Run the Phase 4 SQL in Supabase.")
        print(f"Timetable admin error: {e}")
        return

    if not subjects:
        st.info("No subjects exist yet.")
        return

    st.caption("Choose a class: the subject list and the timetable below show only that class.")
    scope = cascade_filter(subjects, "tt_f", labels={"year": "Study year"})
    if not scope:
        st.warning("No subjects match these filters.")
        return
    scope_ids = {x['subject_id'] for x in scope}
    opts = {_opt_label(x): x for x in scope}

    with st.container(border=True):
        label = st.selectbox("Subject", list(opts.keys()), key="tt_subject")
        c1, c2, c3, c4 = st.columns(4)
        day = c1.selectbox("Day", list(range(7)), format_func=lambda i: DAYS[i], key="tt_day")
        start = c2.time_input("Start", dtime(9, 0), key="tt_start")
        end = c3.time_input("End", dtime(10, 0), key="tt_end")
        room = c4.text_input("Room", key="tt_room")

        if st.button("Add slot", type="primary", icon=":material/add:", key="tt_add"):
            subject = opts[label]
            if end <= start:
                st.error("End time must be after the start time.")
            else:
                clash = _find_clash(slots, subject, day, start.isoformat(), end.isoformat(), room, {})
                if clash:
                    st.error(f"⚠️ Conflict: {clash}")
                else:
                    try:
                        supabase.table('timetables').insert({
                            'subject_id': subject['subject_id'],
                            'day_of_week': day,
                            'start_time': start.isoformat(),
                            'end_time': end.isoformat(),
                            'room': room.strip() or None,
                        }).execute()
                        st.toast("Slot added!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not add slot: {e}")

    st.subheader("Current timetable (selected class)")
    shown = [x for x in slots if x['subject_id'] in scope_ids]
    if not shown:
        st.info("No slots yet for this selection.")
        return
    for d in range(7):
        day_slots = [x for x in shown if x['day_of_week'] == d]
        if not day_slots:
            continue
        with st.container(border=True):
            st.write(f"**{DAYS[d]}**")
            for x in day_slots:
                sub = x.get('subjects') or {}
                a, b = st.columns([6, 1])
                room_txt = f" · Room {x['room']}" if x.get('room') else ""
                a.write(f"🕐 {_hhmm(x['start_time'])}–{_hhmm(x['end_time'])} — {sub.get('name', '?')} "
                        f"({sub.get('course') or '-'} Y{sub.get('year') or '-'} Sec {sub.get('section', '?')}){room_txt}")
                if b.button("Delete", key=f"tt_del_{x['id']}"):
                    supabase.table('timetables').delete().eq('id', x['id']).execute()
                    st.rerun()
