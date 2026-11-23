import streamlit as st

from src.database.config import supabase
from src.services.pure_logic import normalize_phone
from src.services.report_policy import FREQUENCIES, FREQ_LABELS, normalise_frequency


def contact_prefs_ui(student_id):
    try:
        cur = (supabase.table('students')
               .select('phone,parent_phone,alert_opt_in,report_frequency')
               .eq('student_id', student_id).execute().data or [{}])[0]
    except Exception as e:
        print(f"contact prefs load failed: {type(e).__name__}")
        st.warning("Contact settings are not available yet. Ask the administrator to run sql/06_report_frequency.sql.")
        return

    phone = st.text_input("Your mobile (optional)", value=cur.get('phone') or '', key='cp_phone')
    parent_phone = st.text_input("Parent/guardian mobile (optional)",
                                 value=cur.get('parent_phone') or '', key='cp_parent_phone')
    consent = st.checkbox(
        "The owner of each number agrees to receive attendance alerts by WhatsApp/SMS.",
        value=bool(cur.get('alert_opt_in')), key='cp_consent')

    options = list(FREQUENCIES)
    now = normalise_frequency(cur.get('report_frequency'))
    freq = st.radio("How often should your parent receive the attendance report by email?",
                    options, index=options.index(now), format_func=lambda k: FREQ_LABELS[k],
                    key='cp_freq')

    if st.button("Save contact settings", key='cp_save'):
        p1 = normalize_phone(phone) if phone.strip() else None
        p2 = normalize_phone(parent_phone) if parent_phone.strip() else None
        if (phone.strip() and not p1) or (parent_phone.strip() and not p2):
            st.error("Enter valid mobile numbers (10-digit Indian or +country code).")
        elif (p1 or p2) and not consent:
            st.error("Please confirm consent for alerts.")
        else:
            try:
                supabase.table('students').update({
                    'phone': p1, 'parent_phone': p2,
                    'alert_opt_in': bool((p1 or p2) and consent),
                    'report_frequency': freq,
                }).eq('student_id', student_id).execute()
                st.success("Saved.")
            except Exception as e:
                print(f"contact prefs save failed: {type(e).__name__}")
                st.error("Could not save. Try again.")
