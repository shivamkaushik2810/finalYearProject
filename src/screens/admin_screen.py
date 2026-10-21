import html
import pandas as pd
import streamlit as st

from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.components.timetable import admin_timetable_manager
from src.components.student_analytics_ui import student_analytics_tab
from src.components.term_manager import admin_term_manager
from src.components.child_overview import _classes_needed, REQUIRED_PCT
from src.database.config import supabase
from src.database.attendance_status import eligible
from src.database.db import admin_login, get_teachers_by_status, set_teacher_status
from src.services.report_export import df_pdf
from src.services.email_service import _send


def admin_screen():
    style_background_dashboard()
    style_base_layout()
    if "admin_data" in st.session_state:
        admin_dashboard()
    else:
        admin_login_screen()


def _go_home():
    st.query_params.clear()
    st.session_state['login_type'] = None


def admin_login_screen():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn'):
            _go_home()
            st.rerun()

    st.header('Admin Login', text_alignment='center')
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary", icon=":material/passkey:", shortcut="control+enter"):
        admin, msg = admin_login(username, password)
        if admin:
            st.session_state.admin_data = {'id': admin['id'], 'name': admin.get('name') or admin['username'],
                                           'username': admin['username']}
            st.session_state.user_role = 'admin'
            st.session_state.is_logged_in = True
            st.rerun()
        else:
            st.error(msg)
    footer_dashboard()


# ───────────────────────── helpers ─────────────────────────

def _all_rows(table, select, order=None, page=1000):
    """Reads every row (PostgREST returns at most 1000 per request)."""
    out, start = [], 0
    while True:
        q = supabase.table(table).select(select)
        for col in (order or []):
            q = q.order(col)
        rows = q.range(start, start + page - 1).execute().data or []
        out.extend(rows)
        if len(rows) < page:
            break
        start += page
    return out


@st.cache_data(ttl=300, show_spinner="Loading data (cached for 5 minutes)...")
def _cached_rows(table, select, order=()):
    return _all_rows(table, select, list(order))


def _download_pair(df, title, subtitle, base, key):
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{base}.csv", mime="text/csv", key=f"{key}_csv")
    c2.download_button("⬇️ PDF", df_pdf(df, title, subtitle),
                       file_name=f"{base}.pdf", mime="application/pdf", key=f"{key}_pdf")


def _notify_teacher(t, approved):
    email = (t.get('email') or '').strip()
    if not email:
        return
    msg = ("Your teacher account has been approved. You can now log in to SnapClass." if approved
           else "Your teacher account request was not approved. Please contact the administrator.")
    subject = "✅ SnapClass account approved" if approved else "SnapClass account request update"
    plain = f"Dear {t['name']},\n\n{msg}\n\nSnapClass Team"
    body = (f"<p>Dear <b>{html.escape(t['name'])}</b>,</p><p>{html.escape(msg)}</p>"
            f"<p>SnapClass Team</p>")
    try:
        _send(email, subject, body, plain)
    except Exception as e:
        print(f"Teacher notification failed: {e}")


# ───────────────────────── approvals ─────────────────────────

def _teacher_row(t, actions):
    with st.container(border=True):
        cols = st.columns([4] + [1] * len(actions))
        cols[0].write(f"**{t['name']}** (@{t['username']})")
        cols[0].caption(t.get('email') or "No email")
        for col, (label, status, kind) in zip(cols[1:], actions):
            if col.button(label, key=f"{status}_{t['teacher_id']}", type=kind):
                set_teacher_status(t['teacher_id'], status)
                _notify_teacher(t, status == 'approved')
                st.rerun()


def _approvals_tab():
    pending = get_teachers_by_status('pending')
    st.subheader(f"Pending requests ({len(pending)})")
    if not pending:
        st.info("No pending requests.")
    for t in pending:
        _teacher_row(t, [("Approve", "approved", "primary"), ("Reject", "rejected", "secondary")])

    st.divider()
    approved = get_teachers_by_status('approved')
    with st.expander(f"Approved teachers ({len(approved)})"):
        for t in approved:
            _teacher_row(t, [("Revoke", "rejected", "tertiary")])
    rejected = get_teachers_by_status('rejected')
    with st.expander(f"Rejected / revoked ({len(rejected)})"):
        for t in rejected:
            _teacher_row(t, [("Approve", "approved", "primary")])


# ───────────────────────── overview & reports ─────────────────────────

def _overview_tab():
    try:
        subjects = _cached_rows('subjects', 'subject_id, name, subject_code, section, course, year, teacher_id, teachers(name)', ('subject_id',))
        pairs = _cached_rows('admin_pair_stats', 'subject_id, student_id, total, present', ('subject_id', 'student_id'))
        sess = {str(r['subject_id']): r['sessions'] for r in _cached_rows('admin_session_counts', 'subject_id, sessions', ('subject_id',))}
        students = _cached_rows('students', 'student_id, name, roll_no, section, course, year, parent_email', ('student_id',))
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.caption("If this mentions admin_pair_stats or admin_session_counts, run the view SQL in Supabase first.")
        return

    top = st.columns([5, 1])
    top[0].caption("Data is cached for 5 minutes for speed. Press Refresh after new attendance is saved.")
    if top[1].button("Refresh", key="adm_refresh"):
        st.cache_data.clear()
        st.rerun()

    def _opts(rows, field):
        return sorted({str(r[field]).strip() for r in rows if r.get(field) not in (None, '')})

    f1, f2, f3 = st.columns(3)
    course = f1.selectbox("Course", ["All courses"] + _opts(subjects, 'course'), key="adm_course")
    year = f2.selectbox("Year", ["All years"] + _opts(subjects, 'year'), key="adm_year")
    pool = [x for x in subjects
            if (course == "All courses" or str(x.get('course')) == course)
            and (year == "All years" or str(x.get('year')) == year)]
    choice = f3.selectbox("Section", ["All sections"] + _opts(pool, 'section'), key="adm_section")
    sel = [x for x in pool if choice == "All sections" or x.get('section') == choice]
    scope = f"{course} | {year if year == 'All years' else 'Year ' + year} | {choice}"

    ids = {str(x['subject_id']) for x in sel}
    pairs_f = [p for p in pairs if str(p['subject_id']) in ids]
    total_all = sum(p['total'] for p in pairs_f)
    present_all = sum(p['present'] for p in pairs_f)
    avg = round(present_all / total_all * 100, 1) if total_all else 0.0
    sessions = sum(sess.get(i, 0) for i in ids)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Students", len({p['student_id'] for p in pairs_f}))
    c2.metric("Teachers", len(get_teachers_by_status('approved')))
    c3.metric("Subjects", len(sel))
    c4.metric("Sessions", sessions)
    c5.metric("Avg attendance", f"{avg}%")

    # per-subject table
    st.subheader("Subject-wise attendance")
    by_sub = {}
    for p in pairs_f:
        a = by_sub.setdefault(str(p['subject_id']), [0, 0, 0])
        a[0] += 1
        a[1] += p['total']
        a[2] += p['present']
    rows = []
    for x in sel:
        enr, tot, pres = by_sub.get(str(x['subject_id']), [0, 0, 0])
        rows.append({
            "Subject": x['name'], "Code": x['subject_code'], "Course": x.get('course') or "",
            "Year": x.get('year') or "", "Section": x.get('section') or "",
            "Teacher": (x.get('teachers') or {}).get('name', ""),
            "Enrolled": enr, "Sessions": sess.get(str(x['subject_id']), 0),
            "Attendance %": round(pres / tot * 100, 1) if tot else 0.0,
        })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width='stretch')
        _download_pair(df, "Subject-wise Attendance Report", scope, "subject_attendance", "adm_subj")
    else:
        st.info("No subjects for this selection.")

    # defaulters
    st.subheader("Defaulters (all subjects)")
    thr = st.slider("Attendance threshold (%)", 40, 95, REQUIRED_PCT, 5, key="adm_thr")
    info = {x['student_id']: x for x in students}
    agg = {}
    for p in pairs_f:
        a = agg.setdefault(p['student_id'], [0, 0])
        a[0] += p['present']
        a[1] += p['total']
    drows = []
    for sid, (pr, t) in agg.items():
        if t == 0:
            continue
        pct = round(pr / t * 100, 1)
        if pct >= thr or sid not in info:
            continue
        x = info[sid]
        drows.append({"Name": x['name'], "Roll No": x.get('roll_no') or "", "Course": x.get('course') or "",
                      "Year": x.get('year') or "", "Section": x.get('section') or "",
                      "Present/Total": f"{pr}/{t}", "Attendance %": pct,
                      "Classes needed": _classes_needed(pr, t, thr), "Parent email": x.get('parent_email') or ""})
    if not drows:
        st.success(f"No students below {thr}%.")
    else:
        ddf = pd.DataFrame(drows).sort_values("Attendance %")
        st.warning(f"{len(ddf)} student(s) below {thr}%")
        st.dataframe(ddf.head(500), hide_index=True, width='stretch')
        if len(ddf) > 500:
            st.caption("Showing the 500 lowest. The CSV and PDF downloads contain all of them.")
        _download_pair(ddf, "Defaulters Report", f"Below {thr}% - {scope}", "defaulters", "adm_def")


# ───────────────────────── dashboard ─────────────────────────

def admin_dashboard():
    admin = st.session_state.admin_data

    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"Welcome, {admin['name']}")
        if st.button("Logout", type="secondary", key="loginbackbtn"):
            del st.session_state.admin_data
            st.session_state['is_logged_in'] = False
            _go_home()
            st.rerun()

    pending_n = len(get_teachers_by_status('pending'))
    t1, t2, t3, t4, t5 = st.tabs([f"Teacher Approvals ({pending_n})", "Overview & Reports", "Timetable", "Student Analytics", "Academic Terms"])
    with t1:
        _approvals_tab()
    with t2:
        _overview_tab()
    with t3:
        admin_timetable_manager()
    with t4:
        student_analytics_tab()
    with t5:
        admin_term_manager()

    footer_dashboard()
