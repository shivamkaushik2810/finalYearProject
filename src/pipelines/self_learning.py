import numpy as np
import joblib
import os
from collections import Counter
from datetime import datetime
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from src.database.config import supabase
from src.database.db import get_all_students, count_students, _fetch_all
from src.database.students_query import get_students_with_faces


MODEL_PATH = "model.pkl"
LEARNING_LOG_PATH = "learning_log.txt"
REGISTRATION_WEIGHT = 3.0


def log_message(msg):
    """Log training messages"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LEARNING_LOG_PATH, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass


def get_all_training_data():
    """
    Collect training data from student face embeddings.
    Each embedding is used ONCE, with a higher sample weight
    (duplicating rows would leak into cross-validation).
    Returns (X, y, weights, total_students)
    """
    students = get_students_with_faces()

    X, y, w = [], [], []
    for student in students:
        emb = student.get('face_embedding')
        sid = student.get('student_id')
        if emb and sid:
            X.append(emb)
            y.append(sid)
            w.append(REGISTRATION_WEIGHT)

    log_message(f"Registration data: {len(X)} students loaded")

    # Teacher-confirmed detections (genuine new samples of each student)
    sample_count = 0
    try:
        rows = _fetch_all(
            lambda: supabase.table('face_samples').select('student_id, embedding'),
            order=('id',))
        for r in rows:
            if r.get('embedding') and r.get('student_id'):
                X.append(r['embedding'])
                y.append(r['student_id'])
                w.append(1.0)
                sample_count += 1
    except Exception as e:
        log_message(f"face_samples unavailable: {e}")
    log_message(f"Confirmed attendance samples: {sample_count}")

    return X, y, w, count_students()


def train_self_learning_model(training_type="auto"):
    """
    Train the face classifier. Returns (success, accuracy_pct, message).
    Accuracy is only measured when every student has >= 2 samples;
    otherwise it is reported as 0 / N/A (not a fake 100%).
    """
    try:
        log_message(f"Starting {training_type} self-learning training...")

        X, y, w, total_students = get_all_training_data()

        if len(X) == 0:
            return False, 0, "No training data available"

        X_np = np.array(X)
        y_np = np.array(y)
        w_np = np.array(w)

        counts = Counter(y)
        accuracy = None   # None = not measurable

        if len(counts) == 1:
            clf = KNeighborsClassifier(n_neighbors=1, metric='euclidean')
            clf.fit(X_np, y_np)
        else:
            min_count = min(counts.values())
            best_c = 10.0
            if min_count >= 2:
                cv = StratifiedKFold(n_splits=min(3, min_count), shuffle=True, random_state=42)
                best_score = -1
                for C in [0.1, 1.0, 10.0, 100.0]:
                    try:
                        scores = cross_val_score(
                            SVC(kernel='rbf', C=C, gamma='scale'),
                            X_np, y_np, cv=cv, scoring='accuracy'
                        )
                        if scores.mean() > best_score:
                            best_score = scores.mean()
                            best_c = C
                    except Exception:
                        continue
                if best_score >= 0:
                    accuracy = float(best_score)
            clf = SVC(kernel='rbf', C=best_c, gamma='scale')
            clf.fit(X_np, y_np, sample_weight=w_np)

        model_data = {
            'clf':            clf,
            'X':              X_np.tolist(),
            'y':              y_np.tolist(),
            'trained_at':     datetime.now().isoformat(),
            'total_students': total_students,
            'total_samples':  len(X),
            'accuracy':       accuracy if accuracy is not None else 0.0,
            'accuracy_measured': accuracy is not None,
            'training_type':  training_type
        }
        joblib.dump(model_data, MODEL_PATH)

        acc_pct = round(accuracy * 100, 2) if accuracy is not None else 0.0
        note = (f"Trained on {len(X)} samples from {total_students} students"
                + ("" if accuracy is not None else " (accuracy not measurable: need >= 2 samples per student)"))
        try:
            supabase.table('model_training_logs').insert({
                'total_students':  total_students,
                'total_samples':   len(X),
                'accuracy_score':  acc_pct,
                'training_type':   training_type,
                'notes':           note
            }).execute()
        except Exception as db_err:
            log_message(f"Could not save training log: {db_err}")

        msg = (f"Model trained! Students: {total_students}, Samples: {len(X)}, "
               f"Accuracy: {str(round(acc_pct, 1)) + '%' if accuracy is not None else 'N/A'}")
        log_message(msg)
        return True, round(acc_pct, 1), msg

    except Exception as e:
        log_message(f"Training failed: {str(e)}")
        return False, 0, str(e)


def get_model_info():
    """Get current model statistics"""
    try:
        if not os.path.exists(MODEL_PATH):
            return {
                "exists": False, "trained_at": "Never", "total_students": 0,
                "total_samples": 0, "accuracy": 0, "training_type": "none"
            }

        model_data = joblib.load(MODEL_PATH)
        return {
            "exists":         True,
            "trained_at":     model_data.get('trained_at', 'Unknown'),
            "total_students": model_data.get('total_students', 0),
            "total_samples":  len(model_data.get('X', [])),
            "accuracy":       round((model_data.get('accuracy') or 0) * 100, 1),
            "training_type":  model_data.get('training_type', 'manual')
        }
    except Exception:
        return {
            "exists": False, "trained_at": "Error", "total_students": 0,
            "total_samples": 0, "accuracy": 0, "training_type": "error"
        }


def get_training_history():
    """Get past training logs from DB"""
    try:
        res = supabase.table('model_training_logs')\
            .select('*')\
            .order('trained_at', desc=True)\
            .limit(10)\
            .execute()
        return res.data or []
    except Exception:
        return []


def should_auto_retrain():
    """Retrain if never trained, older than 7 days, or new students were added."""
    try:
        if not os.path.exists(MODEL_PATH):
            return True, "Model not found"

        model_data = joblib.load(MODEL_PATH)
        trained_at = model_data.get('trained_at')

        if not trained_at:
            return True, "Training date unknown"

        days_since = (datetime.now() - datetime.fromisoformat(trained_at)).days
        if days_since >= 7:
            return True, f"Model is {days_since} days old"

        last_count    = model_data.get('total_students', 0)
        current_count = count_students()

        if current_count > last_count:
            return True, f"New students added ({current_count - last_count} new)"

        return False, f"Model is up to date (trained {days_since} days ago)"

    except Exception as e:
        return True, f"Check failed: {str(e)}"


def auto_retrain_if_needed():
    """Retrain if needed. Returns (retrained: bool, message: str)"""
    should_train, reason = should_auto_retrain()
    if should_train:
        log_message(f"Auto-retraining triggered: {reason}")
        success, accuracy, msg = train_self_learning_model("auto")
        return success, msg
    return False, reason
