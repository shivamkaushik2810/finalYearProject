import logging
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from src.components.ai_insights import (
    show_attendance_prediction, show_drowsiness_analysis,
    show_emotion_analysis, show_nlp_analytics,
)
from src.components.charts import attendance_trend, subject_bars
from src.components.dialog_add_photo import add_photos_dialog
from src.components.dialog_attendance_results import show_attendance_result
from src.components.dialog_create_subject import create_subject_dialog
from src.components.dialog_share_subject import share_subject_dialog
from src.components.dialog_voice_attendance import voice_attendance_dialog
from src.components.footer import footer_dashboard
from src.components.header import header_dashboard
from src.components.marks_management import show_teacher_marks
from src.components.self_learning_ui import show_self_learning_dashboard
from src.components.subject_card import subject_card
from src.database.config import supabase
from src.database.db import (
    check_teacher_exists, create_teacher, get_attendance_for_teacher,
    get_teacher_subjects, teacher_login,
)
from src.database.ui_queries import get_enrolled_students, get_logs_for_subjects, get_student_names
from src.pipelines.face_pipeline import predict_attendance
from src.pipelines.image_quality import check_image_quality, count_faces_in_image
from src.pipelines.liveness_detection import check_liveness
from src.services import attendance_stats as S
from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.ui.widgets import empty_state, render_password_checklist, stat_cards, stepper

log = logging.getLogger(__name__)

NAV = {
    "overview": ":material/dashboard: Overview",
    "attendance": ":material/photo_camera: Attendance",
    "subjects": ":material/menu_book: Subjects",
    "students": ":material/group: Students",
    "records": ":material/cards_stack: Records",
    "marks": ":material/grade: Marks",
    "insights": ":material/smart_toy: Insights",
}


def teacher_screen():
    style_background_dashboard()
    style_base_layout()

    if "teacher_data" in st.session_state:
        teacher_dashboard()
    elif "teacher_login_type" not in st.session_state or st.session_state.teacher_login_type == "login":
        teacher_screen_login()
    elif st.session_state.teacher_login_type == "register":
        teacher_screen_register()


def _goto(tab):
    st.session_state.teacher_nav = tab


def _logout():
    for key in ("teacher_data", "teacher_nav", "att_step", "att_subject_id", "att_review", "att_notes"):
        st.session_state.pop(key, None)
    st.session_state["is_logged_in"] = False


def teacher_dashboard():
    teacher_data = st.session_state.teacher_data
    teacher_id = teacher_data["teacher_id"]

    c1, c2 = st.columns(2, vertical_alignment="center", gap="large")
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"Welcome, {teacher_data['name']}")
        st.button("Log out", type="secondary", key="danger_logout",
                  shortcut="control+backspace", on_click=_logout)

    with st.spinner("Loading your subjects..."):
        subjects = get_teacher_subjects(teacher_id)

    if "teacher_nav" not in st.session_state:
        st.session_state.teacher_nav = "overview"
    choice = st.segmented_control(
        "Section", list(NAV), format_func=NAV.get, key="teacher_nav",
        label_visibility="collapsed",
    )
    nav = choice or "overview"
    st.divider()

    if nav == "overview":
        teacher_tab_overview(subjects)
    elif nav == "attendance":
        teacher_tab_take_attendance(subjects)
    elif nav == "subjects":
        teacher_tab_manage_subjects(teacher_id, subjects)
    elif nav == "students":
        teacher_tab_enrolled_students(subjects)
    elif nav == "records":
        teacher_tab_attendance_records(teacher_id)
    elif nav == "marks":
        show_teacher_marks(subjects, teacher_id)
    elif nav == "insights":
        teacher_tab_ai_insights(subjects, teacher_id)

    footer_dashboard()


# ---------------------------------------------------------------- overview
def _no_subjects_state():
    empty_state("Create your first subject", "Subjects hold your students, attendance and marks.")
    st.button("Create subject", type="primary", on_click=_goto, args=("subjects",))


def teacher_tab_overview(subjects):
    st.header("Overview")
    if not subjects:
        _no_subjects_state()
        return

    logs = get_logs_for_subjects([s["subject_id"] for s in subjects])
    total = S.overall(logs)
    at_risk = len(S.at_risk_students(logs))
    last = S.last_session(logs)
    last_txt = pd.to_datetime(last, errors="coerce")
    last_txt = "None yet" if last is None or pd.isna(last_txt) else f"{last_txt:%d %b, %I:%M %p}"

    stat_cards([
        ("Subjects", len(subjects), ""),
        ("Average attendance", f"{total['pct']:.0f}%" if total["total"] else "No data",
         "" if not total["total"] else "good" if total["pct"] >= 75 else "avg" if total["pct"] >= 50 else "bad"),
        ("At-risk students", at_risk, "bad" if at_risk else "good"),
        ("Last session", last_txt, ""),
    ])

    by_subject = S.per_subject(logs)
    cols = st.columns(2)
    chart_rows = []
    for i, sub in enumerate(subjects):
        row = by_subject.get(sub["subject_id"], {"present": 0, "total": 0})
        percent = S.pct(row["present"], row["total"])
        chart_rows.append((sub["name"], percent))
        with cols[i % 2]:
            subject_card(sub["name"], sub["subject_code"], sub["section"],
                         stats=[("\U0001FAC2", "Students", sub["total_students"]),
                                ("\U0001F570\uFE0F", "Classes", sub["total_classes"])],
                         pct=percent, total=row["total"])

    c1, c2 = st.columns(2)
    with c1:
        subject_bars(chart_rows)
    with c2:
        attendance_trend(logs)


# ------------------------------------------------------- take attendance
def _reset_attendance_flow():
    st.session_state.att_step = 1
    st.session_state.att_review = None
    st.session_state.att_notes = []


def _run_face_analysis(subject_id):
    """Scan every photo, then build the review rows. Returns (df, logs, notes)."""
    notes, detected_best, sources = [], {}, {}
    for idx, img in enumerate(st.session_state.attendance_images):
        img_np = np.array(img.convert("RGB"))
        _, warnings = check_image_quality(img_np)
        for w in warnings:
            notes.append(f"Photo {idx + 1}: {w}")
        is_live, _, _ = check_liveness(img_np)
        if not is_live:
            notes.append(f"Photo {idx + 1}: possible spoofing detected, so this photo was skipped.")
            continue
        detected, _, _ = predict_attendance(img_np)
        for sid, conf in (detected or {}).items():
            sources.setdefault(sid, []).append(f"Photo {idx + 1}")
            if not isinstance(conf, bool):
                detected_best[sid] = max(detected_best.get(sid, 0.0), float(conf))

    enrolled_res = supabase.table("subject_students").select("*, students(*)") \
        .eq("subject_id", subject_id).execute()
    enrolled = enrolled_res.data or []
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rows, logs = [], []
    for node in enrolled:
        s = node["students"]
        srcs = sources.get(s["student_id"], [])
        present = bool(srcs)
        rows.append({
            "Name": s["name"], "ID": s["student_id"],
            "Match": detected_best.get(s["student_id"]) if present else None,
            "Source": ", ".join(srcs) if present else "-",
            "Status": "Present" if present else "Absent",
        })
        logs.append({"student_id": s["student_id"], "subject_id": subject_id,
                     "timestamp": stamp, "is_present": present})
    return pd.DataFrame(rows), logs, notes


def teacher_tab_take_attendance(subjects):
    st.header("Take attendance")
    if not subjects:
        _no_subjects_state()
        return

    options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    by_id = {s["subject_id"]: s for s in subjects}
    st.session_state.setdefault("att_step", 1)
    st.session_state.setdefault("attendance_images", [])
    step = st.session_state.att_step

    chosen_id = st.session_state.get("att_subject_id")
    if step > 1 and chosen_id not in by_id:
        _reset_attendance_flow()
        step = 1
    stepper(["Subject", "Photos", "Review and confirm"], step)

    if step == 1:
        labels = list(options)
        default = next((l for l, s in options.items() if s["subject_id"] == chosen_id), labels[0])
        label = st.selectbox("Which class is this for?", labels, index=labels.index(default))
        if st.button("Continue", type="primary"):
            st.session_state.att_subject_id = options[label]["subject_id"]
            st.session_state.att_step = 2
            st.rerun()
        return

    subject = by_id[chosen_id]
    st.caption(f"{subject['name']} ({subject['subject_code']})")

    if step == 2:
        images = st.session_state.attendance_images
        counts = st.session_state.setdefault("photo_face_counts", {})
        if images:
            cols = st.columns(4)
            for idx, img in enumerate(images):
                with cols[idx % 4]:
                    if id(img) not in counts:
                        counts[id(img)] = count_faces_in_image(np.array(img.convert("RGB")))
                    faces = counts[id(img)]
                    st.image(img, width="stretch", caption=f"Photo {idx + 1}: {faces} face(s)")
                    if faces == 0:
                        st.warning("No faces found. Retake or remove this photo.")
                    if st.button("Remove", key=f"rm_photo_{idx}", type="tertiary", width="stretch"):
                        images.pop(idx)
                        st.rerun()
        else:
            empty_state("Add class photos", "Take a photo or upload one to scan the class.")

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("Back", type="secondary", width="stretch"):
                st.session_state.att_step = 1
                st.rerun()
        with b2:
            if st.button("Add photos", type="secondary", icon=":material/photo_prints:", width="stretch"):
                add_photos_dialog()
        with b3:
            if st.button("Use voice", type="secondary", icon=":material/mic:", width="stretch"):
                voice_attendance_dialog(subject["subject_id"])
        with b4:
            if st.button("Run face analysis", type="primary", icon=":material/analytics:", width="stretch"):
                if not images:
                    st.warning("Add at least one photo first.")
                else:
                    with st.spinner("Scanning class photos..."):
                        try:
                            df, logs, notes = _run_face_analysis(subject["subject_id"])
                        except Exception:
                            log.exception("Face analysis failed")
                            st.error("The scan didn't finish. Try again, or use fewer photos.")
                            return
                    if not logs:
                        st.warning("No students are enrolled in this subject yet.")
                        return
                    st.session_state.att_review = (df, logs)
                    st.session_state.att_notes = notes
                    st.session_state.att_step = 3
                    st.rerun()

        if st.session_state.get("voice_attendance_results"):
            st.info("Voice attendance results are ready in the voice window.")
        return

    review = st.session_state.get("att_review")
    if not review:
        _reset_attendance_flow()
        st.rerun()
    df, logs = review
    for note in st.session_state.get("att_notes", []):
        st.warning(note)
    if st.button("Back to photos", type="tertiary"):
        st.session_state.att_step = 2
        st.rerun()
    show_attendance_result(df, logs, key_prefix="face_rev", allowed_subject_ids=set(by_id),
                           on_finish=_reset_attendance_flow)


# -------------------------------------------------------------- subjects
def teacher_tab_manage_subjects(teacher_id, subjects):
    col1, col2 = st.columns(2)
    with col1:
        st.header("Manage subjects")
    with col2:
        if st.button("Create new subject", type="primary", width="stretch"):
            create_subject_dialog(teacher_id)

    if not subjects:
        empty_state("No subjects yet", "Create one to start taking attendance.")
        return

    by_subject = S.per_subject(get_logs_for_subjects([s["subject_id"] for s in subjects]))

    def share_button(sub):
        def render():
            if st.button(f"Share code: {sub['name']}", key=f"share_{sub['subject_code']}_{sub['subject_id']}",
                         type="secondary", icon=":material/share:"):
                share_subject_dialog(sub["name"], sub["subject_code"])
        return render

    for sub in subjects:  # every subject is rendered inside the loop
        row = by_subject.get(sub["subject_id"], {"present": 0, "total": 0})
        subject_card(
            name=sub["name"], code=sub["subject_code"], section=sub["section"],
            stats=[("\U0001FAC2", "Students", sub["total_students"]),
                   ("\U0001F570\uFE0F", "Classes", sub["total_classes"])],
            footer_callback=share_button(sub),
            pct=S.pct(row["present"], row["total"]), total=row["total"],
        )


# -------------------------------------------------------------- students
def teacher_tab_enrolled_students(subjects):
    st.header("Enrolled students")
    if not subjects:
        _no_subjects_state()
        return

    options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    label = st.selectbox("Subject", list(options), key="enroll_list_sub")
    sub = options[label]

    enrolled = get_enrolled_students(sub["subject_id"])  # one query
    stats = S.per_student(get_logs_for_subjects([sub["subject_id"]]))  # one paged query

    if not enrolled:
        empty_state("No students yet", "Share the subject code so students can enroll.")
        return

    rows = []
    for s in enrolled:
        st_row = stats.get(s["student_id"], {"present": 0, "total": 0})
        percent = S.pct(st_row["present"], st_row["total"])
        kind, text, icon = S.status_for(percent, st_row["total"])
        rows.append({
            "Name": s.get("name") or "Unknown", "Roll no": s.get("roll_no") or "N/A",
            "Section": s.get("section") or "N/A",
            "Email": "Yes" if s.get("email") else "No",
            "Parent email": "Yes" if s.get("parent_email") else "No",
            "Present": st_row["present"], "Classes": st_row["total"],
            "Attendance %": percent, "Status": f"{icon} {text}", "_kind": kind,
        })
    df = pd.DataFrame(rows)

    stat_cards([
        ("Enrolled", len(df), ""),
        ("With email", int((df["Email"] == "Yes").sum()), ""),
        ("With parent email", int((df["Parent email"] == "Yes").sum()), ""),
        ("At risk", int((df["_kind"] == "risk").sum()), "bad" if (df["_kind"] == "risk").any() else "good"),
    ])

    f1, f2, f3 = st.columns([3, 2, 2], vertical_alignment="bottom")
    with f1:
        search = st.text_input("Search", placeholder="Name or roll number")
    with f2:
        sort = st.selectbox("Sort by", ["Lowest attendance", "Highest attendance", "Name"])
    with f3:
        only_risk = st.toggle("At risk only")

    view = df
    if search:
        q = search.lower()
        view = view[view["Name"].str.lower().str.contains(q, regex=False)
                    | view["Roll no"].astype(str).str.lower().str.contains(q, regex=False)]
    if only_risk:
        view = view[view["_kind"] == "risk"]
    if sort == "Lowest attendance":
        view = view.sort_values("Attendance %")
    elif sort == "Highest attendance":
        view = view.sort_values("Attendance %", ascending=False)
    else:
        view = view.sort_values("Name")

    if view.empty:
        st.info("No students match these filters.")
        return
    st.dataframe(
        view.drop(columns=["_kind"]), hide_index=True, width="stretch",
        column_config={"Attendance %": st.column_config.ProgressColumn(
            "Attendance %", min_value=0, max_value=100, format="%.0f%%")},
    )


# --------------------------------------------------------------- records
def teacher_tab_attendance_records(teacher_id):
    st.header("Attendance records")
    records = get_attendance_for_teacher(teacher_id)
    if not records:
        empty_state("No sessions yet", "Saved attendance sessions will be listed here.")
        return

    rows = []
    for r in records:
        sub = r.get("subjects") or {}
        rows.append({"ts": str(r.get("timestamp") or ""), "subject_id": r.get("subject_id"),
                     "Subject": sub.get("name", "Unknown"), "Code": sub.get("subject_code", ""),
                     "student_id": r.get("student_id"), "present": bool(r.get("is_present"))})
    df = pd.DataFrame(rows)
    df["ts_group"] = df["ts"].str.split(".").str[0]
    when = pd.to_datetime(df["ts_group"], errors="coerce")
    df["when"] = when

    summary = (df.groupby(["ts_group", "subject_id", "Subject", "Code"], dropna=False)
               .agg(Present=("present", "sum"), Total=("present", "count"), when=("when", "min"))
               .reset_index())

    f1, f2, f3 = st.columns([2, 2, 2], vertical_alignment="bottom")
    with f1:
        subject_filter = st.selectbox("Subject", ["All subjects"] + sorted(summary["Subject"].unique()))
    with f2:
        valid = summary["when"].dropna()
        lo = valid.min().date() if not valid.empty else datetime.now().date()
        hi = valid.max().date() if not valid.empty else datetime.now().date()
        span = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    with f3:
        search = st.text_input("Search", placeholder="Subject or code")

    view = summary
    if subject_filter != "All subjects":
        view = view[view["Subject"] == subject_filter]
    if isinstance(span, (tuple, list)) and len(span) == 2:
        view = view[view["when"].isna() | ((view["when"].dt.date >= span[0]) & (view["when"].dt.date <= span[1]))]
    if search:
        q = search.lower()
        view = view[view["Subject"].str.lower().str.contains(q, regex=False)
                    | view["Code"].str.lower().str.contains(q, regex=False)]
    view = view.sort_values("ts_group", ascending=False)

    if view.empty:
        st.info("No sessions match these filters.")
        return

    shown = pd.DataFrame({
        "Time": view["when"].dt.strftime("%d %b %Y, %I:%M %p").fillna("N/A"),
        "Subject": view["Subject"], "Code": view["Code"],
        "Present": view["Present"].astype(int), "Total": view["Total"].astype(int),
    })
    shown["Attendance"] = (shown["Present"] / shown["Total"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(shown, hide_index=True, width="stretch")

    export = shown.copy()
    for col in ("Subject", "Code"):
        export[col] = export[col].map(S.csv_safe)
    st.download_button("Export CSV", export.to_csv(index=False).encode("utf-8"),
                       file_name="attendance_records.csv", mime="text/csv",
                       icon=":material/download:", type="secondary")

    st.subheader("Session details")
    recent = view.head(100)
    labels = {f"{r['when']:%d %b %Y %I:%M %p} | {r['Code']} | {int(r['Present'])}/{int(r['Total'])}"
              if pd.notna(r["when"]) else f"Unknown time | {r['Code']}": (r["ts_group"], r["subject_id"])
              for _, r in recent.iterrows()}
    pick = st.selectbox("Choose a session", list(labels))
    group, subject_id = labels[pick]
    session_rows = df[(df["ts_group"] == group) & (df["subject_id"] == subject_id)]
    names = get_student_names(list(session_rows["student_id"]))

    def fmt(sid):
        s = names.get(sid, {})
        return f"{s.get('name', 'Unknown')} ({s.get('roll_no') or 'N/A'})"

    present_ids = list(session_rows.loc[session_rows["present"], "student_id"])
    absent_ids = list(session_rows.loc[~session_rows["present"], "student_id"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Present ({len(present_ids)})**")
        st.write("\n".join(f"- \u2713 {fmt(i)}" for i in present_ids) or "No one")
    with c2:
        st.markdown(f"**Absent ({len(absent_ids)})**")
        st.write("\n".join(f"- \u2717 {fmt(i)}" for i in absent_ids) or "No one")


# --------------------------------------------------------------- insights
def teacher_tab_ai_insights(subjects, teacher_id):
    st.header("AI insights")

    with st.expander("Send weekly parent reports"):
        st.info("Weekly reports are sent every Monday. You can also send them manually.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Send weekly reports now", type="primary", icon=":material/mail:"):
                from src.services.scheduler import manual_send_weekly_reports
                with st.spinner("Sending weekly reports to all parents..."):
                    success, failed = manual_send_weekly_reports()
                st.success(f"Reports sent. Success: {success}, failed: {failed}")
        with col2:
            st.metric("Next auto send", "Every Monday")
    st.divider()

    if not subjects:
        _no_subjects_state()
        return

    options = {f"{s['name']} - {s['subject_code']}": s for s in subjects}
    label = st.selectbox("Subject", list(options))
    sub = options[label]
    sid = sub["subject_id"]

    enrolled = get_enrolled_students(sid)
    logs = get_logs_for_subjects([sid])
    st.divider()

    t1, t2, t3, t4 = st.tabs(["Prediction and risk", "Ask attendance", "Emotion and alertness", "Self learning"])
    with t1:
        attendance_trend(logs)
        show_attendance_prediction(logs, enrolled)
    with t2:
        show_nlp_analytics(logs, enrolled, sub["name"])
    with t3:
        if st.session_state.get("attendance_images"):
            imgs = [np.array(img.convert("RGB")) for img in st.session_state.attendance_images]
            show_emotion_analysis(imgs)
            st.divider()
            show_drowsiness_analysis(imgs)
        else:
            st.info("Add class photos in the Attendance section first.")
    with t4:
        show_self_learning_dashboard()


# ----------------------------------------------------------- login / register
def login_teacher(username, password):
    if not username or not password:
        return False
    teacher = teacher_login(username, password)
    if teacher:
        st.session_state.user_role = "teacher"
        st.session_state.teacher_data = teacher
        st.session_state.is_logged_in = True
        return True
    return False


def teacher_screen_login():
    c1, c2 = st.columns(2, vertical_alignment="center", gap="large")
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to home", type="secondary", key="loginbackbtn", shortcut="control+backspace"):
            st.session_state["login_type"] = None
            st.rerun()

    st.header("Log in with your password", text_alignment="center")
    st.space()

    teacher_username = st.text_input("Username", placeholder="ananyaroy")
    teacher_pass = st.text_input("Password", type="password", placeholder="Enter your password")
    st.divider()

    btnc1, btnc2 = st.columns(2)
    with btnc1:
        if st.button("Log in", type="primary", icon=":material/passkey:", shortcut="control+enter", width="stretch"):
            if login_teacher(teacher_username, teacher_pass):
                st.toast("Welcome back")
                time.sleep(1)
                st.rerun()
            else:
                st.error("That username and password don't match. Try again.")
    with btnc2:
        if st.button("Register instead", type="secondary", icon=":material/passkey:", width="stretch"):
            st.session_state.teacher_login_type = "register"
            st.rerun()
    footer_dashboard()


def validate_password(password):
    """Check password strength. Returns (is_valid, error_message)"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 16:
        return False, "Password must not exceed 16 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number (0-9)."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', password):
        return False, "Password must contain at least one special character (!@#$%^&* etc)."
    common_words = ["password", "teacher", "admin", "snapclass", "123456", "qwerty", "letmein"]
    if any(word in password.lower() for word in common_words):
        return False, "Password is too common or contains a dictionary word."
    return True, ""


def register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm, teacher_email=None):
    if not teacher_username or not teacher_name or not teacher_pass:
        return False, "All fields are required."
    if teacher_email and not S.valid_email(teacher_email):
        return False, "Enter a valid email address."
    if check_teacher_exists(teacher_username):
        return False, "That username is already taken."
    if teacher_pass != teacher_pass_confirm:
        return False, "The passwords don't match."
    is_valid, pwd_error = validate_password(teacher_pass)
    if not is_valid:
        return False, pwd_error
    try:
        create_teacher(teacher_username, teacher_pass, teacher_name, email=teacher_email or None)
        return True, "Account created. Log in now."
    except Exception:
        log.exception("Teacher registration failed")
        return False, "Couldn't create the account. Try again in a moment."


def teacher_screen_register():
    c1, c2 = st.columns(2, vertical_alignment="center", gap="large")
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to home", type="secondary", key="loginbackbtn", shortcut="control+backspace"):
            st.session_state["login_type"] = None
            st.rerun()

    st.header("Register your teacher profile")
    st.space()

    teacher_username = st.text_input("Username", placeholder="ananyaroy")
    teacher_name = st.text_input("Name", placeholder="Ananya Roy")
    teacher_email = st.text_input("Email", placeholder="teacher@gmail.com",
                                  help="Attendance summaries are sent here after every class.")
    teacher_pass = st.text_input("Password", type="password", placeholder="Choose a password")
    render_password_checklist(teacher_pass)
    teacher_pass_confirm = st.text_input("Confirm password", type="password", placeholder="Type it again")
    st.divider()

    btnc1, btnc2 = st.columns(2)
    with btnc1:
        if st.button("Register now", type="primary", icon=":material/passkey:", shortcut="control+enter", width="stretch"):
            ok, message = register_teacher(teacher_username, teacher_name, teacher_pass,
                                           teacher_pass_confirm, teacher_email)
            if ok:
                st.success(message)
                time.sleep(2)
                st.session_state.teacher_login_type = "login"
                st.rerun()
            else:
                st.error(message)
    with btnc2:
        if st.button("Log in instead", type="secondary", icon=":material/passkey:", width="stretch"):
            st.session_state.teacher_login_type = "login"
            st.rerun()
    footer_dashboard()
