"""Runs inside worker processes. Keep imports minimal: no Streamlit, no Supabase."""
import face_recognition
import numpy as np


def encode_image(args):
    image_np, jitters = args
    locations = face_recognition.face_locations(image_np, model="hog")
    if not locations:
        return 0, []
    encodings = face_recognition.face_encodings(image_np, locations, num_jitters=jitters)
    return len(locations), [np.asarray(e, dtype=float) for e in encodings]
