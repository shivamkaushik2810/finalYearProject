import json
import os
import threading
import time
import traceback
from datetime import datetime

import face_recognition
import numpy as np

from src.database.students_query import get_students_with_faces

SCAN_JITTERS = int(os.environ.get("SCAN_JITTERS", "1"))
_SCAN_SLOTS = threading.BoundedSemaphore(int(os.environ.get("SCAN_CONCURRENCY", "2")))

THRESHOLD = 0.55  # lower = stricter (0.6 is the library default)


def _dbg(msg):
    try:
        with open("face_debug.log", "a") as f:
            f.write(f"[{datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass


def get_face_embeddings(image_np):
    """Extract 128-d face embeddings from image"""
    try:
        locations = face_recognition.face_locations(image_np, model='hog')
        return face_recognition.face_encodings(image_np, locations, num_jitters=3)
    except Exception:
        return []


_KNOWN_LOCK = threading.Lock()
_KNOWN = {"at": 0.0, "val": None}
KNOWN_TTL = float(os.environ.get("KNOWN_FACES_TTL", "60"))


def invalidate_known_faces():
    with _KNOWN_LOCK:
        _KNOWN["val"] = None


def _load_known_faces():
    """Cached so concurrent scans share one DB read (read-only use)."""
    with _KNOWN_LOCK:
        if _KNOWN["val"] is not None and time.monotonic() - _KNOWN["at"] < KNOWN_TTL:
            return _KNOWN["val"]
        val = _load_known_faces_uncached()
        _KNOWN["val"], _KNOWN["at"] = val, time.monotonic()
        return val


def _load_known_faces_uncached():
    ids, embs = [], []
    for s in get_students_with_faces():
        e = s.get('face_embedding')
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except Exception:
                continue
        if e and len(e) == 128:
            ids.append(s['student_id'])
            embs.append(e)
    return ids, np.array(embs, dtype=float)


def _predict_core(image_np, enc_out=None):
    """Bound how many scans do CPU-heavy work at once."""
    with _SCAN_SLOTS:
        return _predict_core_unbounded(image_np, enc_out)


def _predict_core_unbounded(image_np, enc_out=None):
    """Match every face in the image against faces stored in the database.
    Fills enc_out[student_id] = encoding (if a dict is given)."""
    detected, all_ids, num_faces = {}, [], 0
    try:
        locations = face_recognition.face_locations(image_np, model='hog')
        num_faces = len(locations)
        _dbg(f"scan: faces_in_image={num_faces}")
        if num_faces == 0:
            return detected, all_ids, num_faces

        encodings = face_recognition.face_encodings(
            image_np, locations, num_jitters=SCAN_JITTERS
        )
        ids, known = _load_known_faces()
        _dbg(f"known faces loaded={len(ids)}")
        if len(ids) == 0:
            return detected, all_ids, num_faces

        for enc in encodings:
            dists = np.linalg.norm(known - np.array(enc), axis=1)
            i = int(np.argmin(dists))
            _dbg(f"best_dist={dists[i]:.3f} threshold={THRESHOLD}")
            if dists[i] < THRESHOLD:
                sid = ids[i]
                detected[sid] = True
                all_ids.append(sid)
                if enc_out is not None:
                    enc_out[sid] = enc
    except Exception:
        _dbg("ERROR: " + traceback.format_exc().replace("\n", " | "))
        traceback.print_exc()
    return detected, all_ids, num_faces


def predict_attendance(image_np):
    """Returns (detected_dict, all_ids, num_faces)."""
    return _predict_core(image_np)


def predict_attendance_with_encodings(image_np):
    """Returns (detected_dict, all_ids, num_faces, {student_id: encoding})"""
    enc = {}
    detected, all_ids, num_faces = _predict_core(image_np, enc)
    return detected, all_ids, num_faces, enc


def train_classifier():
    """Single trainer: delegates to the self-learning pipeline."""
    try:
        invalidate_known_faces()  # new student must be matchable immediately
        from src.pipelines.self_learning import train_self_learning_model
        ok, _, _ = train_self_learning_model("registration")
        return ok
    except Exception:
        return False
