import pandas as pd
import streamlit as st

from src.database.config import supabase
from src.database.attendance_status import eligible
from src.pipelines.absence_model import (
    fit_model, predict_students, FLAG_THRESHOLD, MEDIUM_THRESHOLD, FEATURES
)
from src.pipelines.attendance_prediction import get_risk_emoji


def _fetch_all_logs(subject_ids, page=1000):
    out, start = [], 0
    while True:
        rows = supabase.table('attendance_logs')\
            .select('student_id, subject_id, is_present, timestamp, status')\
            .in_('subject_id', subject_ids)\
            .order('timestamp').order('subject_id').order('student_id')\
            .range(start, start + page - 1).execute().data or []
        out.extend(rows)
        if len(rows) < page:
            break
        start += page
    return eligible(out)


@st.cache_data(ttl=120, show_spinner="Training absence-risk model...")
def _fit_cached(subject_ids):
    return fit_model(_fetch_all_logs(list(subject_ids)))


def show_ml_absence_risk(subject_ids, logs, enrolled):
    st.subheader("🧠 ML Absence Risk (Logistic Regression)")
    st.caption("Estimates each student's chance of being absent at the next class from their own history "
               "and the class trend. Use it to reach out early, not to penalise anyone.")

    if not subject_ids:
        return
    try:
        result = _fit_cached(tuple(sorted(subject_ids)))
    except Exception as e:
        st.error("Could not train the model right now.")
        print(f"ML risk error: {e!r}")
        return

    if result["status"] != "ok":
        st.info(f"Not enough history to train a reliable model yet: {result['reason']}. "
                "The rule-based view above stays in use until more classes are recorded.")
        return

    m, base = result["metrics"], result["baseline_last"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accuracy (held-out)", f"{m['accuracy'] * 100:.0f}%")
    c2.metric("Absence recall", f"{m['recall'] * 100:.0f}%")
    c3.metric("Absence precision", f"{m['precision'] * 100:.0f}%")
    c4.metric("F1 (absence)", f"{m['f1']:.2f}")

    auc_txt = f"AUC {result['auc']:.2f}. " if result["auc"] is not None else ""
    st.caption(
        f"Trained on {result['n_train']} earlier class records and tested on the {result['n_test']} most recent ones. "
        f"{auc_txt}Baseline rule ('absent last class means absent again'): F1 {base['f1']:.2f}, "
        f"always-'present': {result['baseline_majority_accuracy'] * 100:.0f}% accuracy. "
        f"Flag threshold: {FLAG_THRESHOLD * 100:.0f}%."
    )
    if not result["beats_baseline"]:
        st.warning("The model does not beat the simple 'absent last time' rule on this data yet. "
                   "Treat the predictions as indicative.")
    if result["n_test"] < 15:
        st.warning("The test set is small, so these scores are rough.")

    preds = predict_students(result["model"], logs, enrolled)
    preds.sort(key=lambda d: (d["p"] is None, -(d["p"] or 0)))
    df = pd.DataFrame([{
        "Student": d["name"],
        "Classes": d["sessions"],
        "Attendance %": d["attendance_pct"] if d["attendance_pct"] is not None else "",
        "Chance absent next class": f"{d['p'] * 100:.0f}%" if d["p"] is not None else "n/a",
        "Risk": f"{get_risk_emoji(d['level'])} {d['level'].title()}",
        "Why": d["reasons"],
    } for d in preds])
    st.dataframe(df, hide_index=True, width='stretch')

    chart = {d["name"]: round(d["p"] * 100, 1) for d in preds if d["p"] is not None}
    if chart:
        st.bar_chart(pd.Series(chart))

    with st.expander("How this model works"):
        st.markdown(
            f"- **Features:** {', '.join(FEATURES)}.\n"
            "- **Model:** logistic regression on standardised features, trained on past classes only.\n"
            "- **Evaluation:** time-ordered split (older 70% train, newer 30% test), so it is tested on the 'future'.\n"
            f"- **Risk levels:** High at {FLAG_THRESHOLD * 100:.0f}%+, Medium at {MEDIUM_THRESHOLD * 100:.0f}%+.\n"
            "- **Limits:** small datasets give noisy scores; it sees attendance history only (not illness, "
            "exams or other causes), so flags are prompts to check in, not conclusions."
        )
