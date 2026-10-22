import numpy as np
import streamlit as st
from src.database.config import supabase

MAX_SAMPLES_PER_STUDENT = 15
MIN_CONFIDENCE = 0.60     # confidence = 1 - distance, so distance < 0.40
MIN_NOVELTY    = 0.08     # skip samples nearly identical to an existing one
CHUNK          = 50       # 50 students x 15 samples stays under the 1000-row API cap


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def commit_confirmed_samples(logs):
    """
    Called after the teacher clicks 'Confirm & Save'.
    Stores face encodings of students confirmed present, then retrains.
    Only applies to FACE attendance (voice logs have no confidence_score key).
    Uses batched queries: ~1 select per 50 students, 1 insert, 1 delete.
    Returns number of samples stored.
    """
    pending = st.session_state.get('pending_face_samples')
    if not pending or not logs:
        return 0
    if not any('confidence_score' in l for l in logs):
        return 0

    present = {l['student_id'] for l in logs if l.get('is_present')}
    candidates = {sid: (conf, emb) for sid, (conf, emb) in pending.items()
                  if sid in present and conf >= MIN_CONFIDENCE}

    if not candidates:
        st.session_state.pending_face_samples = {}
        return 0

    # one batched read of existing samples instead of one query per student
    existing_by_sid = {}
    for chunk in _chunks(list(candidates), CHUNK):
        rows = (supabase.table('face_samples')
                .select('id, student_id, embedding')
                .in_('student_id', chunk)
                .order('created_at')
                .execute().data or [])
        for r in rows:
            existing_by_sid.setdefault(r['student_id'], []).append(r)

    new_rows, delete_ids = [], []
    for sid, (conf, emb) in candidates.items():
        existing = existing_by_sid.get(sid, [])
        emb_np = np.array(emb)
        if any(np.linalg.norm(np.array(e['embedding']) - emb_np) < MIN_NOVELTY
               for e in existing):
            continue
        new_rows.append({
            'student_id': sid,
            'embedding':  list(emb),
            'confidence': float(conf),
            'source':     'attendance'
        })
        # keep only the newest MAX_SAMPLES_PER_STUDENT
        excess = len(existing) + 1 - MAX_SAMPLES_PER_STUDENT
        delete_ids.extend(e['id'] for e in existing[:max(0, excess)])

    for chunk in _chunks(new_rows, 200):
        supabase.table('face_samples').insert(chunk).execute()
    for chunk in _chunks(delete_ids, 200):
        supabase.table('face_samples').delete().in_('id', chunk).execute()

    stored = len(new_rows)
    st.session_state.pending_face_samples = {}

    if stored:
        from src.pipelines.self_learning import train_self_learning_model
        train_self_learning_model("learning")

    return stored
