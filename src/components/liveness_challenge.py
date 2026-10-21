import random
import time
import numpy as np
import streamlit as st
import face_recognition
from PIL import Image
from src.pipelines.spoof_guard import detect_spoof

TURN_DELTA = 0.35        # head must turn this much vs the first photo
EAR_CLOSED = 0.20        # eye aspect ratio below this = eyes closed
EAR_OPEN = 0.22          # eye aspect ratio above this = eyes open
FRONT_YAW_MAX = 0.30     # |yaw| must be below this to count as facing the camera
SAME_PERSON_FRONT = 0.6  # face distance limit (frontal photos)
SAME_PERSON_TURN = 0.85  # face distance limit (turned head)
TOTAL_SECONDS = 90       # time allowed for the whole challenge
MAX_FAILS = 3            # failed attempts before the challenge restarts

STEP_TEXT = {
    'turn': "Turn your head about 30-40 degrees to ONE SIDE, then take a photo.",
    'eyes': "Keep your eyes CLOSED, then take a photo.",
    'front': "Look straight at the camera with your eyes OPEN, then take a photo.",
}

_KEYS = ('liveness_steps', 'liveness_idx', 'liveness_start',
         'liveness_attempt', 'liveness_fails')


def _clear_state():
    for k in _KEYS:
        st.session_state.pop(k, None)


def _yaw_value(landmarks):
    nose_x = np.mean([p[0] for p in landmarks['nose_tip']])
    le_x = np.mean([p[0] for p in landmarks['left_eye']])
    re_x = np.mean([p[0] for p in landmarks['right_eye']])
    a = abs(nose_x - le_x) + 1e-6
    b = abs(re_x - nose_x) + 1e-6
    return float(np.log(a / b))


def _ear(eye):
    p = [np.array(x, dtype=float) for x in eye]
    v = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    h = np.linalg.norm(p[0] - p[3]) + 1e-6
    return v / (2.0 * h)


def _analyze(img_np):
    locs = face_recognition.face_locations(img_np, model='hog')
    if len(locs) != 1:
        return None
    lm = face_recognition.face_landmarks(img_np, locs)
    enc = face_recognition.face_encodings(img_np, locs, num_jitters=1)
    if not lm or not enc:
        return None
    lm = lm[0]
    return {
        'yaw': _yaw_value(lm),
        'ear': (_ear(lm['left_eye']) + _ear(lm['right_eye'])) / 2,
        'enc': enc[0],
    }


def _check_step(task, first, second, dist):
    """Returns an error string, or None if the step passed."""
    if task == 'turn':
        if dist > SAME_PERSON_TURN:
            return "This does not look like the same person."
        if abs(second['yaw'] - first['yaw']) < TURN_DELTA:
            return "Head not turned enough. Turn further to one side."
    elif task == 'eyes':
        if dist > SAME_PERSON_FRONT:
            return "This does not look like the same person."
        if second['ear'] > EAR_CLOSED:
            return "Eyes look open. Close them fully and retake."
    else:  # front
        if dist > SAME_PERSON_FRONT:
            return "This does not look like the same person."
        if second['ear'] < EAR_OPEN:
            return "Eyes must be open. Look at the camera and retake."
        if abs(second['yaw']) > FRONT_YAW_MAX:
            return "Face the camera straight on and retake."
    return None


def run_liveness_challenge(frontal_np):
    """Random 3-step challenge. Returns True once every step is passed."""
    if st.session_state.get('liveness_passed'):
        return True

    if 'liveness_steps' not in st.session_state:
        steps = ['turn', 'eyes', 'front']
        random.shuffle(steps)
        st.session_state.liveness_steps = steps
        st.session_state.liveness_idx = 0
        st.session_state.liveness_start = time.time()
        st.session_state.liveness_attempt = 0
        st.session_state.liveness_fails = 0

    steps = st.session_state.liveness_steps
    idx = st.session_state.liveness_idx
    attempt = st.session_state.liveness_attempt
    task = steps[idx]

    st.divider()
    st.subheader("🛡️ Liveness check")
    st.progress(idx / len(steps))
    st.info(f"Step {idx + 1} of {len(steps)}: {STEP_TEXT[task]}")

    shot = st.camera_input("Take the liveness photo", key=f"live_cam_{idx}_{attempt}")
    if not shot:
        return False

    if time.time() - st.session_state.liveness_start > TOTAL_SECONDS:
        st.error("⏱️ Time ran out. The challenge will restart with new steps.")
        if st.button("Restart challenge", key="live_restart_timeout"):
            _clear_state()
            st.rerun()
        return False

    img2 = np.array(Image.open(shot).convert('RGB'))
    is_real, spoof_reason = detect_spoof(img2)
    first = _analyze(frontal_np)
    second = _analyze(img2)

    error = None
    if not is_real:
        error = spoof_reason
    elif first is None or second is None:
        error = "Could not see exactly one face. Try again."
    else:
        dist = float(np.linalg.norm(first['enc'] - second['enc']))
        print(f"[liveness] step={idx + 1}/{len(steps)} task={task} "
              f"yaw1={first['yaw']:.2f} yaw2={second['yaw']:.2f} "
              f"ear2={second['ear']:.2f} dist={dist:.2f}")
        error = _check_step(task, first, second, dist)

    if error is None:
        st.session_state.liveness_idx += 1
        st.session_state.liveness_attempt = 0
        if st.session_state.liveness_idx >= len(steps):
            _clear_state()
            st.session_state.liveness_passed = True
            st.success("✅ Liveness verified")
            return True
        st.rerun()

    st.error(f"❌ {error}")
    if st.button("Try again", key=f"live_retry_{idx}_{attempt}"):
        st.session_state.liveness_fails += 1
        if st.session_state.liveness_fails >= MAX_FAILS:
            _clear_state()  # restart with a new random order
        else:
            st.session_state.liveness_attempt += 1
        st.rerun()
    return False
