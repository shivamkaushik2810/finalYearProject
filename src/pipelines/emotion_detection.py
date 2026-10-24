import importlib.util
import os
from collections import Counter
from functools import lru_cache

import numpy as np
from src.pipelines.face_landmarks_util import detect_faces

# auto | hsemotion | deepface | landmarks
BACKEND_PREF = os.getenv("SNAPCLASS_EMOTION_BACKEND", "auto").lower()
MIN_FACE_PX = 40

_HS_NAMES = {0: "angry", 1: "neutral", 2: "disgust", 3: "fear",
             4: "happy", 5: "neutral", 6: "sad", 7: "surprise"}   # contempt -> neutral
_NAME_MAP = {"anger": "angry", "contempt": "neutral", "disgust": "disgust", "fear": "fear",
             "happiness": "happy", "neutral": "neutral", "sadness": "sad", "surprise": "surprise"}


@lru_cache(maxsize=1)
def _hsemotion():
    if BACKEND_PREF not in ("auto", "hsemotion") or importlib.util.find_spec("hsemotion_onnx") is None:
        return None
    try:
        from hsemotion_onnx.facial_emotions import HSEmotionRecognizer
        return HSEmotionRecognizer(model_name="enet_b0_8_best_afew")
    except Exception:
        return None


@lru_cache(maxsize=1)
def _deepface():
    if BACKEND_PREF not in ("auto", "deepface") or importlib.util.find_spec("deepface") is None:
        return None
    try:
        from deepface import DeepFace
        return DeepFace
    except Exception:
        return None


def get_backend_name():
    if _hsemotion() is not None:
        return "hsemotion"
    if _deepface() is not None:
        return "deepface"
    return "landmarks"


def _crop(img, box, pad_ratio=0.15):
    x, y, w, h = box
    pad = int(pad_ratio * max(w, h))
    H, W = img.shape[:2]
    return np.ascontiguousarray(img[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)])


def _hs_scores(fer, img, box):
    crop = _crop(img, box)
    if crop.size == 0:
        return None
    _, probs = fer.predict_emotions(crop, logits=False)        # RGB crop
    probs = np.asarray(probs, dtype=float).ravel()
    idx_map = getattr(fer, "idx_to_class", None)
    scores = {}
    for i, p in enumerate(probs):
        if idx_map and i in idx_map:
            name = _NAME_MAP.get(str(idx_map[i]).lower(), str(idx_map[i]).lower())
        else:
            name = _HS_NAMES.get(i, "neutral")
        scores[name] = scores.get(name, 0.0) + float(p)
    total = sum(scores.values()) or 1.0
    return {k: v / total * 100.0 for k, v in scores.items()}


def _df_scores(DeepFace, img, box):
    crop = _crop(img, box)
    if crop.size == 0:
        return None
    res = DeepFace.analyze(crop[:, :, ::-1].copy(), actions=["emotion"],
                           enforce_detection=False, detector_backend="skip", silent=True)
    if isinstance(res, list):
        res = res[0]
    return {k.lower(): float(v) for k, v in res["emotion"].items()}


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _landmark_scores(lm):
    """
    Fallback only. Geometry heuristic with a dead zone: unless a signal is clearly strong,
    the answer is 'neutral'. Thresholds are NOT tuned on real data.
    """
    chin = lm["chin"]
    fw = np.linalg.norm(chin[0] - chin[16])
    if fw <= 0:
        return None

    top, bot = lm["top_lip"], lm["bottom_lip"]
    mouth_w = np.linalg.norm(top[0] - top[6]) / fw
    mar = np.linalg.norm(top[9] - bot[9]) / max(np.linalg.norm(top[0] - top[6]), 1e-6)

    center_y = (top[3][1] + bot[3][1]) / 2.0
    corner_y = (top[0][1] + top[6][1]) / 2.0
    lift = (center_y - corner_y) / fw

    lb, rb = lm["left_eyebrow"], lm["right_eyebrow"]
    le, re = lm["left_eye"], lm["right_eye"]
    brow_gap = ((le[:, 1].mean() - lb[:, 1].mean()) + (re[:, 1].mean() - rb[:, 1].mean())) / 2.0 / fw
    slope = (((lb[0][1] - lb[4][1]) + (rb[4][1] - rb[0][1])) / 2.0) / fw

    happy = 0.65 * _clip01((lift - 0.02) / 0.04) + 0.35 * _clip01((mouth_w - 0.42) / 0.08)
    surprise = 0.6 * _clip01((mar - 0.50) / 0.40) + 0.4 * _clip01((brow_gap - 0.12) / 0.04)
    angry = _clip01((-slope - 0.015) / 0.03)
    sad = 0.5 * _clip01((-lift - 0.015) / 0.03) + 0.5 * _clip01((slope - 0.03) / 0.03)

    peak = max(happy, surprise, angry, sad)
    neutral = 1.0 if peak < 0.45 else max(0.05, 0.6 - peak)

    raw = {"happy": happy, "surprise": surprise, "angry": angry, "sad": sad, "neutral": neutral}
    total = sum(raw.values()) or 1.0
    return {k: v / total * 100.0 for k, v in raw.items()}


def detect_emotions(image_np):
    """Returns (results, error). results: [{emotion, confidence, all_scores, position, backend}]"""
    try:
        img, faces = detect_faces(image_np, upsample=1)
        fer, DeepFace = _hsemotion(), _deepface()
        results = []

        for f in faces:
            x, y, w, h = f["box"]
            if w < MIN_FACE_PX:
                continue

            scores, used = None, None
            if fer is not None:
                try:
                    scores, used = _hs_scores(fer, img, f["box"]), "hsemotion"
                except Exception:
                    scores = None
            if scores is None and DeepFace is not None:
                try:
                    scores, used = _df_scores(DeepFace, img, f["box"]), "deepface"
                except Exception:
                    scores = None
            if scores is None:
                scores, used = _landmark_scores(f["landmarks"]), "landmarks"
            if not scores:
                continue

            emotion = max(scores, key=scores.get)
            results.append({
                "emotion": emotion,
                "confidence": round(scores[emotion], 1),
                "all_scores": {k: round(v, 1) for k, v in scores.items()},
                "position": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "backend": used,
            })
        return results, None
    except Exception as e:
        return [], str(e)


def get_emotion_emoji(emotion):
    return {
        "happy": "😊", "sad": "😢", "angry": "😠", "fear": "😨",
        "surprise": "😲", "disgust": "🤢", "neutral": "😐", "unknown": "❓",
    }.get(str(emotion).lower(), "😐")


def get_class_emotion_summary(emotions_list):
    if not emotions_list:
        return {}
    counts = Counter(e["emotion"] for e in emotions_list)
    total = len(emotions_list)
    return {
        "total_faces": total,
        "emotion_counts": dict(counts),
        "dominant_emotion": counts.most_common(1)[0][0],
        "engagement_score": _calc_engagement(counts, total),
    }


def _calc_engagement(counts, total):
    if total == 0:
        return 0
    engaged = counts.get("happy", 0) + counts.get("neutral", 0) + counts.get("surprise", 0)
    return round(engaged / total * 100)
