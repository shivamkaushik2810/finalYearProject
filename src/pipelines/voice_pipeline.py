import io
import librosa
import numpy as np
import streamlit as st
from resemblyzer import VoiceEncoder, preprocess_wav


@st.cache_resource
def load_voice_encoder():
    return VoiceEncoder()


def _unit(a):
    a = np.asarray(a, dtype=np.float64)
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    return a / np.maximum(n, 1e-10)


def _build_matrix(candidates_dict):
    ids = [sid for sid, emb in candidates_dict.items() if emb]
    if not ids:
        return [], None
    return ids, _unit([candidates_dict[s] for s in ids])


def get_voice_embedding(audio_bytes):
    try:
        encoder = load_voice_encoder()
        audio, _ = librosa.load(io.BytesIO(audio_bytes), sr=16000)
        wav = preprocess_wav(audio)
        return encoder.embed_utterance(wav).tolist()
    except Exception:
        st.error("Voice recog error")
        return None


def identify_speaker(new_embedding, candidates_dict, threshold=0.65):
    ids, M = _build_matrix(candidates_dict)
    if new_embedding is None or M is None:
        return None, 0.0
    sims = M @ _unit(new_embedding)
    i = int(sims.argmax())
    score = float(sims[i])
    return (ids[i], score) if score >= threshold else (None, score)


def process_bulk_audio(audio_bytes, candidates_dict, threshold=0.65):
    try:
        ids, M = _build_matrix(candidates_dict)
        if M is None:
            return {}

        encoder = load_voice_encoder()
        sr = 16000
        audio, _ = librosa.load(io.BytesIO(audio_bytes), sr=sr)
        segments = librosa.effects.split(audio, top_db=30)

        embs = []
        for start, end in segments:
            if (end - start) < sr * 0.5:
                continue
            try:
                wav = preprocess_wav(audio[start:end])
                embs.append(encoder.embed_utterance(wav))
            except Exception:
                continue
        if not embs:
            return {}

        sims = _unit(embs) @ M.T                  # (segments, candidates) in one product
        best_idx = sims.argmax(axis=1)
        best_val = sims.max(axis=1)

        results = {}
        for i, score in zip(best_idx, best_val):
            if score >= threshold:
                sid = ids[int(i)]
                if score > results.get(sid, -1.0):
                    results[sid] = float(score)
        return results
    except Exception:
        st.error("Bulk process error")
        return {}
