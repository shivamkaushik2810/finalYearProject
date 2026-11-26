"""Parallel (multi-process) face recognition for many photos.
Encoding runs in worker processes; matching against known faces runs here."""
import numpy as np

from src.pipelines import face_pipeline as fp
from src.pipelines.face_worker import encode_image
from src.services.adaptive_balancer import run_balanced_processes


def predict_many(images):
    """Returns a list aligned with `images`: (detected_dict, all_ids, num_faces),
    or None for a photo that failed. A failed photo is never treated as present."""
    encoded = run_balanced_processes(encode_image, [(im, fp.SCAN_JITTERS) for im in images])
    ids, known = fp._load_known_faces()
    out = []
    for res in encoded:
        if res is None:
            out.append(None)
            continue
        num_faces, encs = res
        detected, all_ids = {}, []
        if num_faces and len(ids):
            for enc in encs:
                dists = np.linalg.norm(known - np.asarray(enc), axis=1)
                i = int(np.argmin(dists))
                if dists[i] < fp.THRESHOLD:
                    detected[ids[i]] = True
                    all_ids.append(ids[i])
        out.append((detected, all_ids, num_faces))
    return out
