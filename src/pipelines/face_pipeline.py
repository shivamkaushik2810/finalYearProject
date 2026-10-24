import json
import traceback
from datetime import datetime
from src.database.students_query import get_students_with_faces
import os
import face_recognition
import joblib
import numpy as np
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from src.database.db import get_all_students

MODEL_PATH = "model.pkl"
THRESHOLD = 0.45
MAX_DIST = 0.6

_cache = {"mtime": None, "data": None}


def get_face_embeddings(image_np, num_jitters=3):
    try:
        locations = face_recognition.face_locations(image_np, model="hog")
        return face_recognition.face_encodings(image_np, locations, num_jitters=num_jitters)
    except Exception:
        return []


def train_classifier():
    try:
        students = get_all_students()
        X, y = [], []
        for st_ in students:
            emb, sid = st_.get("face_embedding"), st_.get("student_id")
            if emb and sid:
                for _ in range(5):
                    X.append(emb)
                    y.append(sid)
        if not X:
            print("No training data!")
            return False

        X_np, y_np = np.array(X), np.array(y)
        n_classes = len(set(y))

        if n_classes == 1:
            clf = KNeighborsClassifier(n_neighbors=1, metric="euclidean").fit(X_np, y_np)
        else:
            best_clf, best_score = None, 0
            for C in (1.0, 10.0, 100.0):
                cand = SVC(kernel="rbf", C=C, gamma="scale")
                try:
                    sc = cross_val_score(cand, X_np, y_np, cv=min(3, n_classes),
                                         scoring="accuracy").mean()
                    if sc > best_score:
                        best_clf, best_score = cand, sc
                except Exception:
                    continue
            clf = (best_clf or SVC(kernel="rbf", C=10.0, gamma="scale")).fit(X_np, y_np)

        joblib.dump({"clf": clf, "X": X_np.tolist(), "y": y_np.tolist()}, MODEL_PATH)
        _cache["mtime"] = None  # force reload
        print(f"Model trained! Students: {len(students)}, Samples: {len(X)}")
        return True
    except Exception as e:
        print(f"Training failed: {e}")
        return False


def _load_model():
    """Loads model.pkl only when the file changed; precomputes index per student."""
    if not os.path.exists(MODEL_PATH):
        train_classifier()
    if not os.path.exists(MODEL_PATH):
        return None
    mtime = os.path.getmtime(MODEL_PATH)
    if _cache["mtime"] != mtime:
        raw = joblib.load(MODEL_PATH)
        X = np.asarray(raw["X"], dtype=np.float64)
        idx = {}
        for i, sid in enumerate(raw["y"]):
            idx.setdefault(sid, []).append(i)
        idx = {k: np.asarray(v) for k, v in idx.items()}
        _cache.update(mtime=mtime, data=(raw["clf"], X, (X ** 2).sum(1), idx))
    return _cache["data"]


def predict_attendance(image_np, num_jitters=3):
    """Returns (detected_dict, all_ids, num_faces)."""
    detected, all_ids, num_faces = {}, [], 0
    try:
        locations = face_recognition.face_locations(image_np, model="hog")
        num_faces = len(locations)
        if not num_faces:
            return detected, all_ids, num_faces

        encodings = face_recognition.face_encodings(image_np, locations, num_jitters=num_jitters)
        if not encodings:
            return detected, all_ids, num_faces

        loaded = _load_model()
        if loaded is None:
            return detected, all_ids, num_faces
        clf, X, X_sq, idx = loaded

        enc = np.asarray(encodings, dtype=np.float64)                    # (F,128)
        D = np.sqrt(np.maximum(X_sq[None, :] + (enc ** 2).sum(1)[:, None]
                               - 2.0 * enc @ X.T, 0.0))                  # (F,N) in one shot
        multi = len(idx) > 1
        svm_preds = clf.predict(enc) if multi else None

        def mark(sid):
            detected[sid] = True
            all_ids.append(sid)

        for f in range(len(enc)):
            d = D[f]
            per_min = {sid: d[ix].min() for sid, ix in idx.items()}

            if not multi:
                sid, dist = next(iter(per_min.items()))
                if dist < MAX_DIST:
                    mark(sid)
                continue

            votes = {}
            best = min(per_min, key=per_min.get)
            if per_min[best] < THRESHOLD:
                votes[best] = 1

            sp = svm_preds[f]
            sp = sp.item() if hasattr(sp, "item") else sp
            votes[sp] = votes.get(sp, 0) + 1

            close = [sid for sid, m in per_min.items() if m <= THRESHOLD]
            if close:
                fr = min(close, key=lambda s: d[idx[s]].mean())
                votes[fr] = votes.get(fr, 0) + 1

            final = max(votes, key=votes.get)
            if votes[final] >= 2 and per_min.get(final, 1.0) < MAX_DIST:
                mark(final)

    except Exception as e:
        print(f"Prediction error: {e}")
    return detected, all_ids, num_faces


def _dbg(msg):
    try:
        with open("face_debug.log", "a") as f:
            f.write(f"[{datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass


def _load_known_faces():
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
            image_np, locations, num_jitters=3
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


def predict_attendance_with_encodings(image_np):
    """Returns (detected_dict, all_ids, num_faces, {student_id: encoding})"""
    enc = {}
    detected, all_ids, num_faces = _predict_core(image_np, enc)
    return detected, all_ids, num_faces, enc
