import numpy as np
import streamlit as st
from src.database.db import get_all_students


@st.cache_resource(ttl=300)
def get_face_index():
    """Load all embeddings ONCE into a matrix + dict. Cached for 5 minutes."""
    students = get_all_students()
    ids, embs, by_id = [], [], {}
    for s in students:
        by_id[s['student_id']] = s
        if s.get('face_embedding'):
            ids.append(s['student_id'])
            embs.append(s['face_embedding'])
    matrix = (np.asarray(embs, dtype=np.float32)
              if embs else np.empty((0, 128), dtype=np.float32))
    return {"ids": ids, "matrix": matrix, "students": by_id}


def invalidate_face_index():
    """Call after a new student registers."""
    get_face_index.clear()


def nearest_student(encoding, threshold=0.45):
    """Vectorized nearest neighbour. Returns (student_id | None, distance)."""
    idx = get_face_index()
    if not idx["ids"]:
        return None, None
    dists = np.linalg.norm(
        idx["matrix"] - np.asarray(encoding, dtype=np.float32), axis=1
    )
    i = int(np.argmin(dists))
    d = float(dists[i])
    return (idx["ids"][i], d) if d < threshold else (None, d)
