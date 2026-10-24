import numpy as np
from src.pipelines.face_landmarks_util import detect_faces

# Tunable thresholds
EAR_CLOSED = 0.18    # below: eyes closed
EAR_DROOPY = 0.22    # below: half-closed
MAR_YAWN   = 0.65    # mouth-open ratio above: yawning
TILT_MAX   = 25.0    # head roll in degrees above: slumping
MIN_FACE_PX = 40     # smaller faces have unreliable landmarks


def _eye_aspect_ratio(eye):
    """EAR = (|p2-p6| + |p3-p5|) / (2*|p1-p4|)"""
    a = np.linalg.norm(eye[1] - eye[5])
    b = np.linalg.norm(eye[2] - eye[4])
    c = np.linalg.norm(eye[0] - eye[3])
    return float((a + b) / (2.0 * c)) if c > 0 else 0.0


def _mouth_ratio(lm):
    top, bot = lm["top_lip"], lm["bottom_lip"]
    width = np.linalg.norm(top[0] - top[6])
    return float(np.linalg.norm(top[9] - bot[9]) / width) if width > 0 else 0.0


def _tilt(lm):
    l = lm["left_eye"].mean(axis=0)
    r = lm["right_eye"].mean(axis=0)
    return float(np.degrees(np.arctan2(r[1] - l[1], r[0] - l[0])))


def detect_drowsiness_simple(image_np, upsample=1):
    """
    Returns list of {"status", "ear_score", "message", "position", "mar", "tilt"}.
    status in: alert / suspicious / drowsy / error
    """
    results = []
    try:
        _, faces = detect_faces(image_np, upsample=upsample)
        for f in faces:
            x, y, w, h = f["box"]
            if w < MIN_FACE_PX:
                continue
            lm = f["landmarks"]
            ear = (_eye_aspect_ratio(lm["left_eye"]) + _eye_aspect_ratio(lm["right_eye"])) / 2.0
            mar = _mouth_ratio(lm)
            tilt = _tilt(lm)

            if ear < EAR_CLOSED:
                status, msg = "drowsy", "😴 Eyes closed — possibly sleeping"
            elif ear < EAR_DROOPY:
                status, msg = "suspicious", "😪 Eyes half-closed — may be drowsy"
            elif mar > MAR_YAWN:
                status, msg = "suspicious", "🥱 Yawning detected"
            elif abs(tilt) > TILT_MAX:
                status, msg = "suspicious", "😪 Head tilted — may be slumping"
            else:
                status, msg = "alert", "✅ Student appears alert"

            results.append({
                "status": status,
                "ear_score": round(ear, 3),
                "message": msg,
                "position": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "mar": round(mar, 3),
                "tilt": round(tilt, 1),
            })
    except Exception as e:
        results.append({
            "status": "error", "ear_score": 0,
            "message": f"Detection failed: {e}", "position": {},
        })
    return results


detect_drowsiness = detect_drowsiness_simple


def get_class_drowsiness_summary(drowsiness_results):
    valid = [r for r in (drowsiness_results or []) if r.get("status") != "error"]
    if not valid:
        return {"total": 0, "alert": 0, "drowsy": 0, "suspicious": 0,
                "alert_pct": 0, "class_status": "No Data"}

    total = len(valid)
    alert = sum(1 for r in valid if r["status"] == "alert")
    drowsy = sum(1 for r in valid if r["status"] == "drowsy")
    suspicious = sum(1 for r in valid if r["status"] == "suspicious")
    alert_pct = round(alert / total * 100)

    if drowsy == 0 and suspicious == 0:
        class_status = "🟢 All detected students appear alert"
    elif alert_pct >= 80:
        class_status = "🟢 Class is highly engaged"
    elif alert_pct >= 50:
        class_status = "🟡 Mixed engagement in class"
    else:
        class_status = "🔴 Low engagement — many students drowsy"

    return {"total": total, "alert": alert, "drowsy": drowsy, "suspicious": suspicious,
            "alert_pct": alert_pct, "class_status": class_status}


def get_drowsiness_emoji(status):
    return {"alert": "✅", "suspicious": "😪", "drowsy": "😴", "error": "❓"}.get(status, "❓")
