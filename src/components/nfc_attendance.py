import streamlit as st

from src.database.config import supabase
from src.components.attendance_scans import record_scan, session_id_of


def _norm(uid):
    return (uid or "").strip().upper().replace(":", "").replace(" ", "").replace("-", "")


def _enrolled(subject_id):
    res = supabase.table('subject_students')\
        .select('student_id, students(student_id, name, roll_no, nfc_uid)')\
        .eq('subject_id', subject_id).execute()
    students = [e['students'] for e in (res.data or []) if e.get('students')]
    students.sort(key=lambda s: ((s.get('roll_no') or ''), s['name']))
    return students


def _on_scan(session, subject_id, key):
    uid = _norm(st.session_state.get(key))
    st.session_state[key] = ""           # clear the box for the next card
    if not uid:
        return
    try:
        match = next((s for s in _enrolled(subject_id) if _norm(s.get('nfc_uid')) == uid), None)
        if not match:
            st.session_state['nfc_msg'] = (False, f"Card {uid} is not linked to any student enrolled in this subject.")
            return
        ok, _ = record_scan(session_id_of(session), match['student_id'], subject_id, 'nfc')
        st.session_state['nfc_msg'] = (
            (True, f"✅ {match['name']} ({match.get('roll_no') or 'N/A'}) marked via NFC.") if ok
            else (False, f"{match['name']} has already tapped."))
    except Exception as e:
        st.session_state['nfc_msg'] = (False, f"NFC error: {e}  (did you run the NFC SQL?)")


def nfc_panel(session, subject_id, boxed=True):
    sid = session_id_of(session)
    key = f"nfc_input_{sid}"
    with (st.expander("📶 NFC / ID card attendance") if boxed else st.container()):
        st.caption("Click the box, then tap a student's card on the USB reader (it types the card number and "
                   "presses Enter). No reader? Type a card number and press Enter to test.")
        st.text_input("Card number", key=key, placeholder="Tap card...",
                      on_change=_on_scan, args=(session, subject_id, key))
        msg = st.session_state.get('nfc_msg')
        if msg:
            (st.success if msg[0] else st.error)(msg[1])

        st.divider()
        st.markdown("**Link a card to a student**")
        try:
            students = _enrolled(subject_id)
        except Exception as e:
            st.error(f"Could not load students: {e}")
            return
        if not students:
            st.caption("No students enrolled.")
            return
        labels = {f"{s.get('roll_no') or 'N/A'} — {s['name']}"
                  + (" (card linked)" if s.get('nfc_uid') else ""): s for s in students}
        pick = st.selectbox("Student", list(labels.keys()), key=f"nfc_pick_{sid}")
        new_uid = _norm(st.text_input("New card number", key=f"nfc_new_{sid}", placeholder="Tap the card here"))
        if st.button("Save card for this student", key=f"nfc_save_{sid}") and new_uid:
            try:
                supabase.table('students').update({'nfc_uid': new_uid})\
                    .eq('student_id', labels[pick]['student_id']).execute()
                st.success(f"Card {new_uid} linked to {labels[pick]['name']}.")
            except Exception as e:
                if 'duplicate' in str(e).lower() or '23505' in str(e):
                    st.error("That card is already linked to another student.")
                else:
                    st.error(f"Could not save: {e}")
