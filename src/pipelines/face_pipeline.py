import face_recognition
import numpy as np
import joblib
import os
from datetime import datetime
from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder
from src.database.db import get_all_students

MODEL_PATH = "model.pkl"
THRESHOLD  = 0.45  # Stricter threshold for better accuracy


def get_face_embeddings(image_np):
    """Extract 128-d face embeddings from image"""
    try:
        # Try CNN model first (more accurate)
        locations = face_recognition.face_locations(image_np, model='hog')
        encodings = face_recognition.face_encodings(image_np, locations, num_jitters=3)
        return encodings
    except Exception:
        return []


def _train_classifier_legacy():
    """Train SVM classifier on all student face embeddings"""
    try:
        students = get_all_students()
        X = []
        y = []

        for student in students:
            emb = student.get('face_embedding')
            sid = student.get('student_id')
            if emb and sid:
                # Add each embedding multiple times for better training
                for _ in range(5):
                    X.append(emb)
                    y.append(sid)

        if len(X) == 0:
            print("No training data!")
            return False

        X_np = np.array(X)
        y_np = np.array(y)

        if len(set(y)) == 1:
            # Only 1 student — use simple nearest neighbor
            from sklearn.neighbors import KNeighborsClassifier
            clf = KNeighborsClassifier(n_neighbors=1, metric='euclidean')
            clf.fit(X_np, y_np)
        else:
            # Multiple students — find best C
            best_clf   = None
            best_score = 0
            for C in [1.0, 10.0, 100.0]:
                clf = SVC(kernel='rbf', C=C, gamma='scale')
                from sklearn.model_selection import cross_val_score
                try:
                    scores = cross_val_score(
                        clf, X_np, y_np,
                        cv=min(3, len(set(y))),
                        scoring='accuracy'
                    )
                    if scores.mean() > best_score:
                        best_score = scores.mean()
                        best_clf   = clf
                except Exception:
                    continue
            if best_clf is None:
                best_clf = SVC(kernel='rbf', C=10.0, gamma='scale')
            best_clf.fit(X_np, y_np)
            clf = best_clf

        model_data = {
            'clf': clf,
            'X':   X_np.tolist(),
            'y':   y_np.tolist(),
            'trained_at': datetime.now().isoformat(),
            'total_students': len(students),
            'training_type': 'registration'
        }
        joblib.dump(model_data, MODEL_PATH)
        print(f"Model trained! Students: {len(students)}, Samples: {len(X)}")
        return True

    except Exception as e:
        print(f"Training failed: {e}")
        return False


def _predict_core(image_np, enc_out=None):
    """
    Predict which students are present in image.
    Returns (detected_dict, all_ids, num_faces)
    Uses multiple validation steps for accuracy.
    """
    detected  = {}
    all_ids   = []
    num_faces = 0

    try:
        # Step 1: Detect faces
        locations = face_recognition.face_locations(image_np, model='hog')
        num_faces = len(locations)

        if num_faces == 0:
            return detected, all_ids, num_faces

        # Step 2: Get embeddings with more jitters for stability
        encodings = face_recognition.face_encodings(
            image_np, locations, num_jitters=3
        )

        if not encodings:
            return detected, all_ids, num_faces

        # Step 3: Load model
        if not os.path.exists(MODEL_PATH):
            train_classifier()

        if not os.path.exists(MODEL_PATH):
            return detected, all_ids, num_faces

        model_data = joblib.load(MODEL_PATH)
        clf        = model_data['clf']
        X_train    = np.array(model_data['X'])
        y_train    = np.array(model_data['y'])

        students = get_all_students()
        student_map = {s['student_id']: s for s in students}

        # Step 4: For each detected face
        for encoding in encodings:
            encoding_np = np.array(encoding)

            # Special case: only 1 student in DB
            if len(set(y_train)) == 1:
                distance = np.linalg.norm(np.array(X_train[0]) - encoding_np)
                if distance < 0.6:
                    sid = y_train[0]
                    detected[sid] = round(float(1 - distance), 2)
                    if enc_out is not None:
                        enc_out[sid] = encoding_np.tolist()
                    all_ids.append(sid)
                    print(f"Single student detected: {student_map.get(sid,{}).get('name','Unknown')} (dist={distance:.3f})")
                continue

            # Method 1: Find nearest neighbor using Euclidean distance
            min_dist   = float('inf')
            best_match = None

            for i, stored_emb in enumerate(X_train):
                dist = np.linalg.norm(np.array(stored_emb) - encoding_np)
                if dist < min_dist:
                    min_dist   = dist
                    best_match = y_train[i]

            # Method 2: SVM prediction with confidence
            if len(set(y_train)) > 1:
                svm_pred = clf.predict([encoding_np])[0]
            else:
                svm_pred = y_train[0]

            # Method 3: face_recognition compare_faces
            # Get unique student embeddings
            unique_students = {}
            for i, sid in enumerate(y_train):
                if sid not in unique_students:
                    unique_students[sid] = []
                unique_students[sid].append(X_train[i])

            best_fr_match  = None
            best_fr_score  = float('inf')

            for sid, embs in unique_students.items():
                # Compare with all embeddings for this student
                matches = face_recognition.compare_faces(
                    embs, encoding_np, tolerance=THRESHOLD
                )
                distances = face_recognition.face_distance(embs, encoding_np)
                if any(matches):
                    avg_dist = np.mean(distances)
                    if avg_dist < best_fr_score:
                        best_fr_score  = avg_dist
                        best_fr_match  = sid

            # Step 5: Voting — all 3 methods must agree or 2 out of 3
            votes = {}
            if best_match and min_dist < THRESHOLD:
                votes[best_match] = votes.get(best_match, 0) + 1
            if svm_pred:
                votes[svm_pred] = votes.get(svm_pred, 0) + 1
            if best_fr_match:
                votes[best_fr_match] = votes.get(best_fr_match, 0) + 1

            if not votes:
                continue

            # Pick student with most votes
            final_match = max(votes, key=votes.get)
            vote_count  = votes[final_match]

            # Need at least 2 out of 3 votes
            if vote_count >= 2:
                # Extra validation: distance must be reasonable
                final_dist = np.linalg.norm(
                    np.array(list(unique_students[final_match])[0]) - encoding_np
                ) if final_match in unique_students else 1.0

                if final_dist < 0.6:
                    detected[final_match] = round(float(1 - final_dist), 2)
                    if enc_out is not None:
                        enc_out[final_match] = encoding_np.tolist()
                    all_ids.append(final_match)
                    confidence = round(1 - final_dist, 2)
                    print(f"Detected: {student_map.get(final_match, {}).get('name', 'Unknown')} "
                          f"(dist={final_dist:.3f}, votes={vote_count}/3, conf={confidence})")

    except Exception as e:
        print(f"Prediction error: {e}")

    return detected, all_ids, num_faces


def predict_attendance(image_np):
    """Returns (detected_dict, all_ids, num_faces)"""
    return _predict_core(image_np)


def predict_attendance_with_encodings(image_np):
    """Returns (detected_dict, all_ids, num_faces, {student_id: encoding})"""
    enc = {}
    detected, all_ids, num_faces = _predict_core(image_np, enc)
    return detected, all_ids, num_faces, enc


def train_classifier():
    """Single trainer: delegates to the self-learning pipeline."""
    from src.pipelines.self_learning import train_self_learning_model
    ok, _, _ = train_self_learning_model("registration")
    return ok
