import cv2
import numpy as np


def detect_emotions(image_np):
    """
    Emotion detection using OpenCV facial features.
    """
    try:
        # Ensure RGB numpy array
        if hasattr(image_np, 'convert'):
            image_np = np.array(image_np.convert('RGB'))

        # Resize if too small
        h, w = image_np.shape[:2]
        if w < 300:
            scale = 300 / w
            image_np = cv2.resize(image_np, (int(w*scale), int(h*scale)))

        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        # Improve contrast
        gray = cv2.equalizeHist(gray)

        face_cascade  = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')
        eye_cascade   = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)
        )

        results = []

        for (fx, fy, fw, fh) in faces:
            face_gray = gray[fy:fy+fh, fx:fx+fw]
            face_rgb  = image_np[fy:fy+fh, fx:fx+fw]

            # Detect smile in lower half of face
            lower_face = face_gray[fh//2:, :]
            smiles = smile_cascade.detectMultiScale(
                lower_face, scaleFactor=1.5, minNeighbors=8, minSize=(15, 15)
            )

            # Detect eyes in upper half of face
            upper_face = face_gray[:fh//2, :]
            eyes = eye_cascade.detectMultiScale(
                upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(10, 10)
            )

            has_smile = len(smiles) > 0
            eye_count = len(eyes)

            # Brightness analysis
            brightness = np.mean(face_gray)

            # Forehead region - check for raised eyebrows (surprise)
            forehead = face_gray[:fh//4, :]
            forehead_bright = np.mean(forehead)

            # Determine emotion
            if has_smile:
                emotion    = "happy"
                confidence = 88.0
            elif eye_count >= 2 and brightness > 100:
                emotion    = "neutral"
                confidence = 72.0
            elif eye_count >= 2 and brightness <= 100:
                emotion    = "sad"
                confidence = 65.0
            elif eye_count == 1:
                emotion    = "neutral"
                confidence = 55.0
            else:
                emotion    = "neutral"
                confidence = 50.0

            results.append({
                "emotion":    emotion,
                "confidence": confidence,
                "all_scores": {
                    "happy":    88.0 if has_smile else 5.0,
                    "neutral":  72.0 if not has_smile else 8.0,
                    "sad":      60.0 if brightness <= 100 else 5.0,
                    "angry":    5.0,
                    "surprise": 5.0
                },
                "position": {
                    "x": int(fx), "y": int(fy),
                    "w": int(fw), "h": int(fh)
                }
            })

        return results, None

    except Exception as e:
        return [], str(e)


def get_emotion_emoji(emotion):
    return {
        "happy":    "😊",
        "sad":      "😢",
        "angry":    "😠",
        "fear":     "😨",
        "surprise": "😲",
        "disgust":  "🤢",
        "neutral":  "😐",
        "unknown":  "❓"
    }.get(emotion.lower(), "😐")


def get_class_emotion_summary(emotions_list):
    if not emotions_list:
        return {}
    from collections import Counter
    all_emotions = [e['emotion'] for e in emotions_list]
    counts       = Counter(all_emotions)
    total        = len(all_emotions)
    return {
        "total_faces":      total,
        "emotion_counts":   dict(counts),
        "dominant_emotion": counts.most_common(1)[0][0] if counts else "neutral",
        "engagement_score": _calc_engagement(counts, total)
    }


def _calc_engagement(counts, total):
    if total == 0:
        return 0
    engaged = counts.get('happy', 0) + counts.get('neutral', 0) + counts.get('surprise', 0)
    return round((engaged / total) * 100)
