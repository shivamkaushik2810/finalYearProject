import cv2
import numpy as np
import face_recognition


def to_rgb_array(img):
    """Accepts PIL image or numpy array, returns contiguous uint8 RGB array."""
    if hasattr(img, "convert"):
        img = np.array(img.convert("RGB"))
    img = np.asarray(img)
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    if img.shape[2] == 4:
        img = img[:, :, :3]
    return np.ascontiguousarray(img.astype(np.uint8))


def _detect_on(arr, upsample):
    locs = face_recognition.face_locations(arr, number_of_times_to_upsample=upsample, model="hog")
    lms = face_recognition.face_landmarks(arr, locs) if locs else []
    return list(zip(locs, lms))


def _to_faces(items, dx, dy, inv):
    """Map detections back to original-image coordinates: (v * inv) + (dx, dy)."""
    off = np.array([dx, dy], dtype=float)
    out = []
    for (t, r, b, l), lm in items:
        out.append({
            "box": (int(l * inv + dx), int(t * inv + dy), int((r - l) * inv), int((b - t) * inv)),
            "landmarks": {k: np.array(v, dtype=float) * inv + off for k, v in lm.items()},
        })
    return out


def _dedupe(faces):
    kept = []
    for f in sorted(faces, key=lambda f: f["box"][2] * f["box"][3], reverse=True):
        x, y, w, h = f["box"]
        cx, cy = x + w / 2, y + h / 2
        dup = False
        for k in kept:
            kx, ky, kw, kh = k["box"]
            if abs(cx - (kx + kw / 2)) < 0.5 * min(w, kw) and abs(cy - (ky + kh / 2)) < 0.5 * min(h, kh):
                dup = True
                break
        if not dup:
            kept.append(f)
    return kept


def _positions(total, side):
    step = max(1, int(side * 0.5))
    pos = list(range(0, max(1, total - side + 1), step))
    if pos[-1] != max(0, total - side):
        pos.append(max(0, total - side))
    return pos


def detect_faces(img, upsample=1, max_side=1600, fallback=True):
    """
    Returns (rgb_image, faces). Each face = {"box": (x, y, w, h), "landmarks": {name: ndarray (n,2)}}
    in ORIGINAL image coordinates.
    Pass 1: normal. Pass 2: upsample=2. Pass 3: overlapping square tiles (tall/wide photos, small faces).
    """
    img = to_rgb_array(img)
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
    inv = 1.0 / scale

    faces = _to_faces(_detect_on(small, upsample), 0, 0, inv)

    if not faces and fallback:
        faces = _to_faces(_detect_on(small, 2), 0, 0, inv)

    if not faces and fallback:
        H, W = small.shape[:2]
        side = min(H, W)
        if max(H, W) > side * 1.3:
            found = []
            for y0 in _positions(H, side):
                for x0 in _positions(W, side):
                    tile = np.ascontiguousarray(small[y0:y0 + side, x0:x0 + side])
                    found += _to_faces(_detect_on(tile, 2), x0 * inv, y0 * inv, inv)
            faces = _dedupe(found)

    return img, faces
