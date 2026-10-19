import numpy as np
import streamlit as st
from src.database.config import supabase

MAX_SAMPLES_PER_STUDENT = 15
MIN_CONFIDENCE = 0.60     # confidence = 1 - distance, so distance < 0.40
MIN_NOVELTY    = 0.08     # skip samples nearly identical to an existing one


def commit_confirmed_samples(logs):
    """
    Called after the teacher clicks 'Confirm & Save'.
    Stores face encodings of students confirmed present, then retrains.
    Only applies to FACE attendance (voice logs have no confidence_score key).
    Returns number of samples stored.
    """
    pending = st.session_state.get('pending_face_samples')
    if not pending or not logs:
        return 0
    if not any('confidence_score' in l for l in logs):
        return 0

    present = {l['student_id'] for l in logs if l.get('is_present')}
    stored = 0

    for sid, (conf, emb) in pending.items():
        if sid not in present or conf < MIN_CONFIDENCE:
            continue

        existing = supabase.table('face_samples')\
            .select('id, embedding')\
            .eq('student_id', sid)\
            .order('created_at')\
            .execute().data or []

        emb_np = np.array(emb)
        if any(np.linalg.norm(np.array(e['embedding']) - emb_np) < MIN_NOVELTY for e in existing):
            continue

        supabase.table('face_samples').insert({
            'student_id': sid,
            'embedding':  list(emb),
            'confidence': float(conf),
            'source':     'attendance'
        }).execute()
        stored += 1

        # keep only the newest MAX_SAMPLES_PER_STUDENT
        excess = len(existing) + 1 - MAX_SAMPLES_PER_STUDENT
        for old in existing[:max(0, excess)]:
            supabase.table('face_samples').delete().eq('id', old['id']).execute()

    st.session_state.pending_face_samples = {}

    if stored:
        from src.pipelines.self_learning import train_self_learning_model
        train_self_learning_model("learning")

    return stored
