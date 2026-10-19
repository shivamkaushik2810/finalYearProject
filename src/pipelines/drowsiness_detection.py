import cv2
import numpy as np

try:
    import dlib
    DLIB_AVAILABLE = True
except ImportError:
    DLIB_AVAILABLE = False


def _eye_aspect_ratio(eye_points):
    """
    Calculate Eye Aspect Ratio (EAR).
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    Low EAR = eye closed = drowsy
    """
    # Vertical distances
    A = np.linalg.norm(eye_points[1] - eye_points[5])
    B = np.linalg.norm(eye_points[2] - eye_points[4])
    # Horizontal distance
    C = np.linalg.norm(eye_points[0] - eye_points[3])
    ear = (A + B) / (2.0 * C)
    return ear


def detect_drowsiness_simple(image_np):
    """
    Simple drowsiness detection using OpenCV Haar cascades.
    Works without dlib.
    Returns list of {"status", "ear_score", "message", "position"}
    """
    results = []
    try:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

        # Load cascades
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )

        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )

        for (fx, fy, fw, fh) in faces:
            face_roi = gray[fy:fy+fh, fx:fx+fw]

            # Detect eyes within face region
            eyes = eye_cascade.detectMultiScale(
                face_roi,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(20, 20)
            )

            eye_count = len(eyes)

            # Analyze eye openness using pixel intensity
            eye_scores = []
            for (ex, ey, ew, eh) in eyes:
                eye_roi    = face_roi[ey:ey+eh, ex:ex+ew]
                # Darker pixels in eye region = more open eye
                mean_intensity = np.mean(eye_roi)
                eye_scores.append(mean_intensity)

            if eye_count == 0:
                status  = "drowsy"
                score   = 0.1
                message = "😴 No eyes detected — possibly sleeping"
            elif eye_count == 1:
                status  = "suspicious"
                score   = 0.2
                message = "😪 Only one eye detected — possibly drowsy"
            else:
                # Both eyes detected — check average brightness
                avg_score = np.mean(eye_scores) if eye_scores else 128
                # Normalize score to 0-1 range
                score = min(avg_score / 128, 1.0)

                if score > 0.6:
                    status  = "alert"
                    message = "✅ Student appears alert"
                elif score > 0.3:
                    status  = "suspicious"
                    message = "😪 Student may be drowsy"
                else:
                    status  = "drowsy"
                    message = "😴 Student appears to be sleeping"

            results.append({
                "status":    status,
                "ear_score": round(score, 2),
                "message":   message,
                "position":  {"x": int(fx), "y": int(fy),
                               "w": int(fw), "h": int(fh)}
            })

    except Exception as e:
        results.append({
            "status":    "error",
            "ear_score": 0,
            "message":   f"Detection failed: {str(e)}",
            "position":  {}
        })

    return results


def get_class_drowsiness_summary(drowsiness_results):
    """
    Summarize drowsiness across all detected faces.
    Returns summary dict
    """
    if not drowsiness_results:
        return {
            "total":        0,
            "alert":        0,
            "drowsy":       0,
            "suspicious":   0,
            "alert_pct":    0,
            "class_status": "No Data"
        }

    total      = len(drowsiness_results)
    alert      = sum(1 for r in drowsiness_results if r['status'] == 'alert')
    drowsy     = sum(1 for r in drowsiness_results if r['status'] == 'drowsy')
    suspicious = sum(1 for r in drowsiness_results if r['status'] == 'suspicious')
    alert_pct  = round((alert / total) * 100) if total > 0 else 0

    if total == 0:
        class_status = "⚪ No faces detected"
    elif drowsy == 0 and suspicious == 0:
        class_status = "🟢 All detected students appear alert"
    elif alert_pct >= 80:
        class_status = "🟢 Class is highly engaged"
    elif alert_pct >= 50:
        class_status = "🟡 Mixed engagement in class"
    else:
        class_status = "🔴 Low engagement — many students drowsy"

    return {
        "total":        total,
        "alert":        alert,
        "drowsy":       drowsy,
        "suspicious":   suspicious,
        "alert_pct":    alert_pct,
        "class_status": class_status
    }


def get_drowsiness_emoji(status):
    return {
        "alert":      "✅",
        "suspicious": "😪",
        "drowsy":     "😴",
        "error":      "❓"
    }.get(status, "❓")
