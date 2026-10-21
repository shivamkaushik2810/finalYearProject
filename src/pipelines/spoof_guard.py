import numpy as np
import streamlit as st
import face_recognition

from src.pipelines.liveness_detection import detect_screen_or_photo as _legacy_check

try:
    from ultralytics import YOLO
    _YOLO_ERR = None
except Exception as e:
    YOLO = None
    _YOLO_ERR = str(e)

_YOLO_OK = YOLO is not None

SCREEN_NAMES = {"cell phone", "tv", "laptop"}
LOG_CONF = 0.10          # log everything above this
REJECT_CONF = 0.15       # reject screens above this
MIN_FACE_OVERLAP = 0.5   # fraction of the face box covered by the screen box
MAX_BIG_SCREEN_RATIO = 8.0
FAIL_CLOSED = True       # block login if the phone detector cannot run


@st.cache_resource
def _load_model():
    return YOLO("yolov8n.pt")  # downloads ~6MB on first run (needs internet)


def _overlap_fraction(face, box):
    fx1, fy1, fx2, fy2 = face
    bx1, by1, bx2, by2 = box
    ix1, iy1 = max(fx1, bx1), max(fy1, by1)
    ix2, iy2 = min(fx2, bx2), min(fy2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area = max(1, (fx2 - fx1) * (fy2 - fy1))
    return inter / area


def _detect(image_np, log):
    if not _YOLO_OK:
        log.append(f"YOLO NOT AVAILABLE: {_YOLO_ERR}")
        if FAIL_CLOSED:
            return False, "Phone detector is not installed/working. Ask the admin to fix it."
        return _legacy_check(image_np)

    locs = face_recognition.face_locations(image_np, model='hog')
    log.append(f"faces found: {len(locs)}")
    if not locs:
        return True, "no face (handled by face pipeline)"

    t, r, b, l = max(locs, key=lambda x: (x[2] - x[0]) * (x[1] - x[3]))
    face = (l, t, r, b)
    face_area = (r - l) * (b - t)
    log.append(f"face box: {face}, image: {image_np.shape[1]}x{image_np.shape[0]}")

    try:
        model = _load_model()
        res = model.predict(image_np[:, :, ::-1].copy(), conf=LOG_CONF, verbose=False)[0]
    except Exception as e:
        log.append(f"YOLO ERROR: {e}")
        if FAIL_CLOSED:
            return False, "Phone detector failed to run. See the debug box."
        return _legacy_check(image_np)

    if len(res.boxes) == 0:
        log.append("YOLO saw no objects at all")
    for box in res.boxes:
        name = model.names[int(box.cls[0])]
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        overlap = _overlap_fraction(face, (x1, y1, x2, y2))
        ratio = ((x2 - x1) * (y2 - y1)) / max(1, face_area)
        log.append(f"object={name} conf={conf:.2f} face_overlap={overlap:.2f} box/face={ratio:.1f}")

        if name in SCREEN_NAMES and conf >= REJECT_CONF and overlap >= MIN_FACE_OVERLAP:
            if name == "cell phone" or ratio <= MAX_BIG_SCREEN_RATIO:
                return False, ("A phone/screen showing a face was detected. "
                               "Please show your REAL face directly to the camera.")

    return _legacy_check(image_np)


def detect_spoof(image_np):
    """Returns (is_real, reason). Shows a debug box with what the detector saw."""
    log = []
    try:
        result = _detect(image_np, log)
    except Exception as e:
        log.append(f"UNEXPECTED ERROR: {e}")
        result = (False, "Spoof check error. See the debug box.") if FAIL_CLOSED else (True, "skipped")
    log.append(f"RESULT: real={result[0]} reason={result[1]}")
    print("[spoof_guard]\n  " + "\n  ".join(log))
    with st.expander("🔧 Spoof debug (remove later)", expanded=not result[0]):
        st.code("\n".join(log))
    return result
