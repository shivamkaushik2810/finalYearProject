"""Accuracy page for the teacher tools. Shows measured numbers only; no student names are displayed."""
import streamlit as st

from src.database.config import supabase
from src.features.accuracy import logic
from src.services.db_utils import fetch_all

DEFAULT_THRESHOLD = 0.55          # same value face_pipeline.py uses to accept a match


def _vec(e):
    if isinstance(e, str):
        import json
        try:
            e = json.loads(e)
        except Exception:
            return None
    return list(e) if e and len(e) == 128 else None


@st.cache_data(ttl=120, show_spinner="Loading face data...")
def _load_people():
    """refs = enrolled faces (registration + extra angles); probes = teacher-confirmed attendance samples."""
    cols = "student_id, face_embedding, face_embeddings"
    try:
        studs = fetch_all(lambda: supabase.table("students").select(cols)
                          .not_.is_("face_embedding", "null").order("student_id"))
    except Exception:                                   # extra-angles column not migrated yet
        studs = fetch_all(lambda: supabase.table("students").select("student_id, face_embedding")
                          .not_.is_("face_embedding", "null").order("student_id"))
    people = {}
    for s in studs:
        refs = [v for v in (_vec(e) for e in [s.get("face_embedding")] + list(s.get("face_embeddings") or [])) if v]
        if refs:
            people[str(s["student_id"])] = {"refs": refs, "probes": []}
    try:
        samples = fetch_all(lambda: supabase.table("face_samples").select("id, student_id, embedding").order("id"))
    except Exception:
        samples = []
    for r in samples:
        v, sid = _vec(r.get("embedding")), str(r.get("student_id"))
        if v and sid in people:
            people[sid]["probes"].append(v)
    return people


def show_accuracy_page():
    st.subheader("🎯 Face recognition accuracy")
    st.caption("Measured on faces already in your database: each confirmed attendance sample is compared with "
               "the student's enrolled faces (genuine) and with every other student's (impostor). "
               "Lower distance = more similar.")
    try:
        people = _load_people()
    except Exception as e:
        print(f"accuracy load failed: {type(e).__name__}")
        st.error("Could not load face data.")
        return
    thr = st.slider("Match threshold (accept if distance is below)", 0.30, 0.80, DEFAULT_THRESHOLD, 0.01,
                    key="acc_thr")
    res = logic.evaluate(people, thr)
    if res["status"] != "ok":
        st.info(res["reason"])
        return
    t = res["at_threshold"]
    c = st.columns(4)
    c[0].metric("False accept rate (FAR)", f"{t['far'] * 100:.2f}%", help="Impostors wrongly accepted")
    c[1].metric("False reject rate (FRR)", f"{t['frr'] * 100:.2f}%", help="Real students wrongly rejected")
    c[2].metric("Rank-1 identification", f"{res['rank1']['rate'] * 100:.1f}%")
    c[3].metric("Equal error rate", f"{res['eer']['eer'] * 100:.2f}%" if res["eer"] else "n/a")
    st.caption(f"{res['genuine']} genuine and {res['impostor']} impostor comparisons from "
               f"{res['students_with_samples']} students with samples (of {res['students']} enrolled). "
               "Small samples give rough numbers; do not quote them as a benchmark.")
    import pandas as pd
    df = pd.DataFrame(res["curve"]).set_index("threshold")[["far", "frr"]] * 100
    st.line_chart(df.rename(columns={"far": "FAR %", "frr": "FRR %"}))
