import streamlit as st
from datetime import datetime
from src.pipelines.self_learning import (
    train_self_learning_model,
    get_model_info,
    get_training_history,
    auto_retrain_if_needed
)


def show_self_learning_dashboard():
    """Show self-learning model dashboard in teacher AI Insights"""

    st.subheader("🧠 Self-Learning Model")
    st.caption("The model automatically improves by learning from confirmed attendance results")

    # Get current model info
    info = get_model_info()

    # Model Status Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status = "✅ Active" if info['exists'] else "❌ Not Trained"
        st.metric("Model Status", status)
    with col2:
        st.metric("Total Students", info['total_students'])
    with col3:
        st.metric("Training Samples", info['total_samples'])
    with col4:
        acc = f"{info['accuracy']}%" if info['accuracy'] > 0 else "N/A"
        st.metric("Model Accuracy", acc)

    # Last trained info
    if info['exists'] and info['trained_at'] != 'Unknown':
        try:
            dt = datetime.fromisoformat(info['trained_at'])
            trained_str = dt.strftime("%d %B %Y, %I:%M %p")
        except Exception:
            trained_str = info['trained_at']
        st.info(f"🕐 Last trained: **{trained_str}** | Type: **{info['training_type']}**")

    st.divider()

    # Auto retrain check
    col1, col2 = st.columns(2)

    with col1:
        st.write("**🔄 Manual Retrain**")
        st.caption("Retrain model with all current student data + confirmed attendance")
        if st.button("🚀 Retrain Model Now", type="primary", key="retrain_btn"):
            with st.spinner("🧠 Training model on all data..."):
                success, accuracy, msg = train_self_learning_model("manual")
            if success:
                st.success(f"✅ {msg}")
                st.balloons()
            else:
                st.error(f"❌ Training failed: {msg}")

    with col2:
        st.write("**🤖 Auto Retrain Check**")
        st.caption("Check if model needs retraining based on new data")
        if st.button("🔍 Check & Auto Retrain", type="secondary", key="auto_retrain_btn"):
            with st.spinner("Checking model status..."):
                retrained, message = auto_retrain_if_needed()
            if retrained:
                st.success(f"✅ Model retrained! {message}")
            else:
                st.info(f"ℹ️ {message}")

    st.divider()

    # How self learning works
    with st.expander("📖 How Self-Learning Works"):
        st.markdown("""
        ### 🧠 Self-Learning Process

        **Step 1 — Registration Data (Base Training)**
        - When a student registers, their face embedding is saved
        - This embedding is used 3 times (higher weight) as base training data

        **Step 2 — Attendance Learning**
        - Every time teacher confirms attendance, results are saved to DB
        - High-confidence detections (score > 0.7) are added as new training samples
        - More attendance sessions = more training data = better accuracy

        **Step 3 — Auto Retraining**
        - Model auto-retrains when:
          - New students are registered
          - Model is more than 7 days old
          - Manual retrain triggered by teacher

        **Step 4 — Improved SVM**
        - System tries multiple C values (0.1, 1.0, 10.0, 100.0)
        - Picks best performing configuration using cross-validation
        - Saves best model automatically

        **Result:** Model gets smarter with every attendance session! 🎯
        """)

    # Training History
    st.write("**📊 Training History (Last 10)**")
    history = get_training_history()

    if not history:
        st.info("No training history yet. Click 'Retrain Model Now' to start!")
    else:
        for h in history:
            try:
                dt  = datetime.fromisoformat(h['trained_at'].replace('Z',''))
                dts = dt.strftime("%d %b %Y, %I:%M %p")
            except Exception:
                dts = h.get('trained_at', 'Unknown')

            col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
            with col1:
                st.write(f"🕐 {dts}")
            with col2:
                st.write(f"👥 {h.get('total_students', 0)} students")
            with col3:
                st.write(f"📊 {h.get('accuracy_score', 0)}%")
            with col4:
                badge = "🤖 Auto" if h.get('training_type') == 'auto' else "👨‍🏫 Manual"
                st.write(badge)
