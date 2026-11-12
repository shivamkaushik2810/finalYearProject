import numpy as np
import streamlit as st
from PIL import Image

from src.pipelines.face_pipeline import get_face_embeddings, train_classifier
from src.pipelines.liveness_detection import detect_screen_or_photo
from src.services.face_embeddings import add_face_angle, all_embeddings, MAX_EMBEDDINGS


@st.dialog("Improve face recognition")
def add_angles_dialog(student_id):
    have = len(all_embeddings(st.session_state.get('student_data', {})))
    st.write(f"Samples saved: **{have}/{MAX_EMBEDDINGS}**. Add 3-5 photos: front, slightly left, "
             "slightly right, with and without glasses. One real face per photo.")
    photo = st.camera_input("Take a photo", key=f"angle_cam_{have}")
    if photo and st.button("Save this angle", type="primary", width="stretch"):
        img = np.array(Image.open(photo).convert("RGB"))
        is_real, reason = detect_screen_or_photo(img)
        if not is_real:
            st.error(reason)
            return
        encs = get_face_embeddings(img)
        if len(encs) != 1:
            st.error("Exactly one face must be visible.")
            return
        ok, msg, row = add_face_angle(student_id, encs[0].tolist())
        if ok:
            st.session_state.student_data = row
            train_classifier()
            st.success(msg)
        else:
            st.error(msg)
