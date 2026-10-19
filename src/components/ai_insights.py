import streamlit as st
import numpy as np
from PIL import Image

from src.pipelines.image_quality import check_image_quality, count_faces_in_image, get_image_quality_score
from src.pipelines.emotion_detection import detect_emotions, get_emotion_emoji, get_class_emotion_summary
from src.pipelines.drowsiness_detection import detect_drowsiness_simple, get_class_drowsiness_summary, get_drowsiness_emoji
from src.pipelines.liveness_detection import check_liveness, get_liveness_badge
from src.pipelines.attendance_prediction import predict_absent_risk, get_risk_emoji, get_subject_health
from src.pipelines.nlp_analytics import answer_query




def show_image_quality_check(image_np):
    """Show image quality analysis before running attendance"""
    st.subheader("🔍 Image Quality Check")

    score = get_image_quality_score(image_np)
    is_good, warnings = check_image_quality(image_np)
    face_count = count_faces_in_image(image_np)

    col1, col2, col3 = st.columns(3)
    with col1:
        color = "green" if score >= 70 else "orange" if score >= 40 else "red"
        st.metric("Quality Score", f"{score}/100")
    with col2:
        st.metric("Faces Detected", f"{face_count} 👥")
    with col3:
        st.metric("Status", "✅ Good" if is_good else "⚠️ Issues Found")

    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("✅ Image quality is good for face recognition!")

    return is_good, face_count


def show_liveness_check(image_np):
    """Show liveness/anti-spoofing check"""
    st.subheader("🛡️ Anti-Spoofing Check")
    is_live, score, reason = check_liveness(image_np)
    badge = get_liveness_badge(is_live, score)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Liveness Score", f"{score}/100")
    with col2:
        st.metric("Result", badge)

    if not is_live:
        st.error(f"🚨 {reason} — Attendance blocked!")
    else:
        st.success(f"{reason}")

    return is_live


def show_emotion_analysis(images_np_list):
    """Show emotion analysis for all uploaded photos"""
    st.subheader("😊 Class Emotion Analysis")
    st.caption("Indicative only: heuristic facial-feature analysis, not a trained emotion model.")

    all_emotions = []
    for img in images_np_list:
        # Ensure image is numpy array in RGB format
        if hasattr(img, 'convert'):
            img = np.array(img.convert('RGB'))
        elif not isinstance(img, np.ndarray):
            img = np.array(img)
        emotions, error = detect_emotions(img)
        if emotions:
            all_emotions.extend(emotions)

    if not all_emotions:
        st.info("No emotions detected — make sure photos show clear faces in good lighting.")
        return

    summary = get_class_emotion_summary(all_emotions)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Faces Analyzed", summary.get('total_faces', 0))
    with col2:
        dominant = summary.get('dominant_emotion', 'unknown')
        st.metric("Dominant Emotion", f"{get_emotion_emoji(dominant)} {dominant.title()}")
    with col3:
        st.metric("Engagement Score", f"{summary.get('engagement_score', 0)}%")

    # Show emotion breakdown
    emotion_counts = summary.get('emotion_counts', {})
    if emotion_counts:
        st.write("**Emotion Breakdown:**")
        cols = st.columns(len(emotion_counts))
        for i, (emotion, count) in enumerate(emotion_counts.items()):
            with cols[i]:
                st.metric(
                    f"{get_emotion_emoji(emotion)} {emotion.title()}",
                    count
                )


def show_drowsiness_analysis(images_np_list):
    """Show drowsiness detection for all uploaded photos"""
    st.subheader("😴 Student Alertness Check")
    st.caption("Indicative only: based on eye detection in a still photo; closed eyes or angle can cause false flags.")

    all_results = []
    for img in images_np_list:
        results = detect_drowsiness_simple(img)
        all_results.extend(results)

    if not all_results:
        st.info("No faces detected for alertness check.")
        return

    summary = get_class_drowsiness_summary(all_results)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Faces", summary['total'])
    with col2:
        st.metric("✅ Alert", summary['alert'])
    with col3:
        st.metric("😪 Suspicious", summary['suspicious'])
    with col4:
        st.metric("😴 Drowsy", summary['drowsy'])

    st.info(summary['class_status'])


def show_attendance_prediction(attendance_logs, enrolled_students):
    """Show attendance risk prediction"""
    st.subheader("📊 Attendance Risk Prediction")
    st.caption("Rule-based risk levels from each student's current attendance percentage.")

    if not attendance_logs:
        st.info("Take at least one attendance session to see predictions.")
        return

    predictions = predict_absent_risk(attendance_logs, enrolled_students)
    health      = get_subject_health(attendance_logs, len(enrolled_students))

    # Subject health
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Class Health Score", f"{health['health_score']}%")
    with col2:
        st.metric("Status", health['status'])
    st.info(f"💡 {health['recommendation']}")

    # Student risk table
    st.write("**Student Risk Levels:**")
    for pred in predictions:
        emoji = get_risk_emoji(pred['risk_level'])
        col1, col2, col3 = st.columns([3, 2, 5])
        with col1:
            st.write(f"{emoji} **{pred['name']}**")
        with col2:
            st.write(f"{pred['attendance_pct']}%")
        with col3:
            st.write(pred['message'])


def show_nlp_analytics(attendance_logs, enrolled_students, subject_name):
    """Show NLP-powered attendance query interface"""
    st.subheader("🤖 Ask About Attendance")
    st.caption("Ask anything about attendance in plain English!")

    # Example queries
    with st.expander("💡 Example Questions"):
        st.write("""
        - Who was absent the most?
        - How many students were present today?
        - Which students are at risk?
        - What is the attendance rate?
        - Who has the best attendance?
        - Who has the worst attendance?
        """)

    query = st.text_input(
        "Ask a question",
        placeholder="e.g. Who was absent the most this month?"
    )

    if st.button("🔍 Get Answer", type="primary") and query:
        with st.spinner("Analyzing attendance data..."):
            answer, data = answer_query(
                query=query,
                attendance_logs=attendance_logs,
                enrolled_students=enrolled_students,
                subject_name=subject_name
            )
        st.success(answer)
