import hashlib
import io
import logging
import time

import numpy as np
import streamlit as st
from PIL import Image

from src.components.dialog_enroll import enroll_dialog
from src.components.footer import footer_dashboard
from src.components.header import header_dashboard
from src.components.marks_management import show_student_marks
from src.components.student_attendance_list import show_student_attendance_list
from src.components.subject_card import subject_card
from src.database.db import (
    create_student, get_student_attendance, get_student_subjects, unenroll_student_to_subject,
)
from src.database.ui_queries import get_student_by_id
from src.pipelines.face_pipeline import get_face_embeddings, predict_attendance, train_classifier
from src.pipelines.liveness_detection import detect_screen_or_photo
from src.pipelines.voice_pipeline import get_voice_embedding
from src.services import attendance_stats as S
from src.services.otp_service import is_email_verified, mark_email_verified, send_and_save_otp, verify_otp
from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.ui.widgets import confirm_dialog, empty_state, stat_cards, stepper

log = logging.getLogger(__name__)

OTP_COOLDOWN_SECONDS = 30
REG_STEPS = ["Personal", "Verify email", "Parent", "Voice"]
SECTIONS = ["A", "B", "C", "D", "E", "F"]
COURSES = ["B.Tech", "M.Tech", "MCA", "BCA", "MBA", "B.Sc", "M.Sc"]
YEARS = ["1", "2", "3", "4"]


# ---------------------------------------------------------------- dashboard
def _logout():
    for key in ("student_data", "reg", "reg_step", "reg_errs", "scan_cache"):
        st.session_state.pop(key, None)
    st.session_state["is_logged_in"] = False


def student_dashboard():
    student_data = st.session_state.student_data
    student_id = student_data["student_id"]

    c1, c2 = st.columns(2, vertical_alignment="center", gap="large")
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"Welcome, {student_data['name']}")
        st.button("Log out", type="secondary", key="danger_student_logout",
                  shortcut="control+backspace", on_click=_logout)

    with st.spinner("Loading your subjects..."):
        subjects = get_student_subjects(student_id)
        logs = get_student_attendance(student_id)

    stats_map = {}
    for entry in logs:
        row = stats_map.setdefault(entry["subject_id"], {"total": 0, "attended": 0})
        row["total"] += 1
        if entry.get("is_present"):
            row["attended"] += 1

    total = sum(v["total"] for v in stats_map.values())
    attended = sum(v["attended"] for v in stats_map.values())
    overall = S.pct(attended, total)
    risk = sum(1 for v in stats_map.values() if v["total"] and S.pct(v["attended"], v["total"]) < 75)
    tone = {"good": "good", "avg": "avg", "risk": "bad"}.get(S.status_for(overall, total)[0], "")
    stat_cards([
        ("Overall attendance", f"{overall:.0f}%" if total else "No data", tone),
        ("Classes attended", f"{attended} / {total}", ""),
        ("Subjects at risk", risk, "bad" if risk else "good"),
        ("Enrolled subjects", len(subjects), ""),
    ])

    tab1, tab2, tab3 = st.tabs(["My subjects", "My attendance", "My marks"])

    with tab1:
        h1, h2 = st.columns(2)
        with h1:
            st.header("Your subjects")
        with h2:
            if st.button("Enroll in a subject", type="primary", width="stretch"):
                enroll_dialog()
        st.divider()

        if not subjects:
            empty_state("Join your first subject", "Use a subject code from your teacher to enroll.")
        else:
            cols = st.columns(2)
            for i, node in enumerate(subjects):
                sub = node["subjects"]
                sid = sub["subject_id"]
                stats = stats_map.get(sid, {"total": 0, "attended": 0})
                percent = S.pct(stats["attended"], stats["total"])

                def unenroll_button(sid=sid, name=sub["name"]):
                    if st.button("Unenroll from this course", type="tertiary", width="stretch",
                                 icon=":material/delete_forever:", key=f"unenroll_{sid}"):
                        def do_it():
                            unenroll_student_to_subject(student_id, sid)
                            st.toast(f"Unenrolled from {name}")
                        confirm_dialog(f"Unenroll from {name}? Your past attendance stays on record.",
                                       "Unenroll", do_it, key=f"unenroll_{sid}")

                with cols[i % 2]:
                    subject_card(
                        name=sub["name"], code=sub["subject_code"], section=sub["section"],
                        stats=[("\U0001F4C5", "Total", stats["total"]), ("\u2705", "Attended", stats["attended"])],
                        footer_callback=unenroll_button, pct=percent, total=stats["total"],
                    )
                    if stats["total"] and percent < 75:
                        need = S.classes_needed(stats["attended"], stats["total"])
                        st.caption(f"Attend the next {need} class(es) in a row to reach 75%.")

    with tab2:
        show_student_attendance_list(student_id)

    with tab3:
        show_student_marks(student_id)

    footer_dashboard()


# ------------------------------------------------------------ registration
def _otp_verify_section(email, purpose, label, name="User"):
    if is_email_verified(email, purpose):
        st.success(f"{label} verified")
        return True

    sent_key = f"otp_sent_at_{purpose}"
    col1, col2 = st.columns([2, 1], vertical_alignment="bottom")
    with col1:
        otp_input = st.text_input(f"Enter the 6-digit code sent to {email}", max_chars=6,
                                  placeholder="123456", key=f"otp_{purpose}")
    with col2:
        sent_at = st.session_state.get(sent_key)
        if st.button("Resend code" if sent_at else "Send code", key=f"send_otp_{purpose}", type="secondary"):
            wait = OTP_COOLDOWN_SECONDS - (time.time() - sent_at) if sent_at else 0
            if wait > 0:
                st.warning(f"You can request a new code in {int(wait) + 1} seconds.")
            elif not S.valid_email(email):
                st.warning("Enter a valid email first.")
            else:
                with st.spinner("Sending code..."):
                    try:
                        send_and_save_otp(email, purpose, name)
                        st.session_state[sent_key] = time.time()
                        st.success(f"Code sent to {email}")
                    except Exception:
                        log.exception("OTP send failed for purpose=%s", purpose)
                        st.error("Couldn't send the code. Check the email address and try again.")

    if otp_input and len(otp_input) == 6:
        if st.button("Verify code", key=f"verify_{purpose}", type="primary"):
            is_valid, message = verify_otp(email, otp_input, purpose)
            if is_valid:
                mark_email_verified(email, purpose)
                st.rerun()
            else:
                st.error(message)
    return False


def _field_error(errs, field):
    if errs.get(field):
        st.caption(f":red[{errs[field]}]")


def _scan_photo(photo_source):
    """Scan once per photo. Streamlit reruns on every click, so cache the result by photo hash."""
    raw = photo_source.getvalue()
    key = hashlib.sha256(raw).hexdigest()
    cache = st.session_state.setdefault("scan_cache", {})
    if key in cache:
        return cache[key]
    img = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    is_real, reason = detect_screen_or_photo(img)
    result = {"is_real": is_real, "reason": reason, "detected": {}, "num_faces": 0}
    if is_real:
        detected, _, num_faces = predict_attendance(img)
        result.update(detected=dict(detected or {}), num_faces=num_faces)
    cache.clear()
    cache[key] = result
    return result


def _registration_wizard(photo_source):
    reg = st.session_state.setdefault("reg", {})
    step = st.session_state.setdefault("reg_step", 1)
    errs = st.session_state.get("reg_errs", {})

    with st.container(border=True):
        st.header("Register new profile")
        stepper(REG_STEPS, step)

        if step == 1:
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full name", value=reg.get("name", ""), placeholder="Your full name")
                _field_error(errs, "name")
                email = st.text_input("Your email", value=reg.get("email", ""), placeholder="student@gmail.com")
                _field_error(errs, "email")
            with c2:
                roll = st.text_input("Roll number", value=reg.get("roll", ""), placeholder="123456789")
                _field_error(errs, "roll")
                section = st.selectbox("Section", SECTIONS, index=SECTIONS.index(reg.get("section", "A")))
            c3, c4 = st.columns(2)
            with c3:
                course = st.selectbox("Course", COURSES, index=COURSES.index(reg.get("course", COURSES[0])))
            with c4:
                year = st.selectbox("Year", YEARS, index=YEARS.index(reg.get("year", "1")))
            if st.button("Continue", type="primary", key="reg_next_1"):
                reg.update(name=name.strip(), email=email.strip(), roll=roll.strip(),
                           section=section, course=course, year=year)
                e = {}
                if not reg["name"]:
                    e["name"] = "Enter your full name."
                if not S.valid_email(reg["email"]):
                    e["email"] = "Enter a valid email address."
                if not reg["roll"]:
                    e["roll"] = "Enter your roll number."
                st.session_state.reg_errs = e
                if not e:
                    st.session_state.reg_step = 2
                st.rerun()

        elif step == 2:
            st.write(f"We'll verify **{reg['email']}** so you can receive attendance emails.")
            verified = _otp_verify_section(reg["email"], "student_email", "Student email", reg["name"] or "Student")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_2"):
                    st.session_state.reg_step = 1
                    st.rerun()
            with b2:
                if st.button("Continue", type="primary", key="reg_next_2"):
                    if verified:
                        st.session_state.reg_errs = {}
                        st.session_state.reg_step = 3
                    else:
                        st.session_state.reg_errs = {"otp": "Verify your email to continue."}
                    st.rerun()
            _field_error(errs, "otp")

        elif step == 3:
            c1, c2 = st.columns(2)
            with c1:
                pname = st.text_input("Parent name", value=reg.get("parent_name", ""), placeholder="Parent or guardian")
                _field_error(errs, "parent_name")
            with c2:
                pemail = st.text_input("Parent email", value=reg.get("parent_email", ""), placeholder="parent@gmail.com")
                _field_error(errs, "parent_email")
            st.info("A weekly attendance report is sent to this email every Monday.")
            pemail_ok = S.valid_email(pemail) and pemail.strip().lower() != reg["email"].lower()
            verified = _otp_verify_section(pemail.strip(), "parent_email", "Parent email", pname or "Parent") \
                if pemail_ok else False
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_3"):
                    reg.update(parent_name=pname.strip(), parent_email=pemail.strip())
                    st.session_state.reg_step = 2
                    st.rerun()
            with b2:
                if st.button("Continue", type="primary", key="reg_next_3"):
                    reg.update(parent_name=pname.strip(), parent_email=pemail.strip())
                    e = {}
                    if not reg["parent_name"]:
                        e["parent_name"] = "Enter your parent's name."
                    if not S.valid_email(reg["parent_email"]):
                        e["parent_email"] = "Enter a valid email address."
                    elif reg["parent_email"].lower() == reg["email"].lower():
                        e["parent_email"] = "Use your parent's email, not your own."
                    elif not is_email_verified(reg["parent_email"], "parent_email"):
                        e["parent_email"] = "Verify this email to continue."
                    st.session_state.reg_errs = e
                    if not e:
                        st.session_state.reg_step = 4
                    st.rerun()

        else:
            st.subheader("Voice enrollment (optional)")
            st.info("Enroll your voice to be marked present by voice attendance. You can skip this.")
            audio_data = None
            try:
                audio_data = st.audio_input("Record: 'I am present, my name is ...'")
            except Exception:
                st.error("Audio recording isn't available right now. You can skip this step.")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Back", type="secondary", key="reg_back_4"):
                    st.session_state.reg_step = 3
                    st.rerun()
            with b2:
                if st.button("Create account", type="primary", key="reg_create"):
                    _create_account(reg, photo_source, audio_data)


def _create_account(reg, photo_source, audio_data):
    with st.spinner("Creating your profile..."):
        img = np.array(Image.open(io.BytesIO(photo_source.getvalue())).convert("RGB"))
        encodings = get_face_embeddings(img)
        if not encodings:
            st.error("Couldn't read your face from the photo. Retake it facing the camera.")
            return
        voice_emb = get_voice_embedding(audio_data.read()) if audio_data else None
        try:
            response = create_student(
                reg["name"], face_embedding=encodings[0].tolist(), voice_embedding=voice_emb,
                email=reg["email"], roll_no=reg["roll"], section=reg["section"],
                parent_email=reg["parent_email"], parent_name=reg["parent_name"],
                year=reg["year"], course=reg["course"])
        except Exception:
            log.exception("Student creation failed")
            st.error("Couldn't create your profile. Try again in a moment.")
            return
        if response:
            train_classifier()
            st.session_state.is_logged_in = True
            st.session_state.user_role = "student"
            st.session_state.student_data = response[0]
            for key in ("reg", "reg_step", "reg_errs", "scan_cache"):
                st.session_state.pop(key, None)
            st.toast(f"Profile created. Hi {response[0]['name']}")
            time.sleep(1)
            st.rerun()


# -------------------------------------------------------------------- screen
def student_screen():
    style_background_dashboard()
    style_base_layout()

    if "student_data" in st.session_state:
        student_dashboard()
        return

    c1, c2 = st.columns(2, vertical_alignment="center", gap="large")
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to home", type="secondary", key="loginbackbtn", shortcut="control+backspace"):
            st.session_state["login_type"] = None
            st.rerun()

    st.header("Log in with FaceID", text_alignment="center")
    st.space()

    show_registration = False
    photo_source = st.camera_input("Position your face in the center")

    with st.expander("Camera not working?"):
        st.write("1. Allow camera access for this site in your browser's address bar.\n"
                 "2. Close other apps or tabs that are using the camera.\n"
                 "3. Select Retry below. If it still fails, ask your teacher for help.")
        st.button("Retry camera", type="secondary", key="retry_camera")

    if photo_source:
        with st.spinner("Scanning your face..."):
            try:
                scan = _scan_photo(photo_source)
            except Exception:
                log.exception("Face scan failed")
                scan = None
        if scan is None:
            st.error("The scan didn't finish. Retake the photo and try again.")
        elif not scan["is_real"]:
            st.error(scan["reason"])
            st.warning("Show your real face to the camera. Photos and phone screens are not accepted.")
        elif scan["num_faces"] == 0:
            st.warning("No face found. Center your face in the frame.")
        elif scan["num_faces"] > 1:
            st.warning("More than one face found. Only one person at a time.")
        elif scan["detected"]:
            student = get_student_by_id(list(scan["detected"].keys())[0])
            if student:
                st.session_state.is_logged_in = True
                st.session_state.user_role = "student"
                st.session_state.student_data = student
                st.session_state.pop("scan_cache", None)
                st.toast(f"Welcome back {student['name']}")
                time.sleep(1)
                st.rerun()
        else:
            st.info("We don't recognize this face yet. Register below to get started.")
            show_registration = True

    if show_registration:
        _registration_wizard(photo_source)

    footer_dashboard()
