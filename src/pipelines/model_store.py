"""Safe, shared access to the trained face model (model.pkl)."""
import contextlib
import logging
import os
import tempfile
import threading
import time

import joblib
import numpy as np

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

log = logging.getLogger("snapclass.model")

MODEL_PATH = os.environ.get("MODEL_PATH", "model.pkl")
_LOCK_PATH = MODEL_PATH + ".lock"

_thread_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache = {"sig": None, "model": None}


@contextlib.contextmanager
def training_lock(timeout=0.0):
    """Exclusive training lock (threads + processes). Yields True if acquired,
    False if still held by someone else after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not _thread_lock.acquire(blocking=False):
        if time.monotonic() >= deadline:
            yield False
            return
        time.sleep(0.1)
    handle = None
    try:
        if fcntl is not None:
            handle = open(_LOCK_PATH, "a+")
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        yield False
                        return
                    time.sleep(0.1)
        yield True
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()
        _thread_lock.release()


def save_model(model_data):
    """Write to a temp file then atomically swap it in, so readers never see
    a half-written model.pkl."""
    directory = os.path.dirname(os.path.abspath(MODEL_PATH))
    fd, tmp_path = tempfile.mkstemp(prefix="model.", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        joblib.dump(model_data, tmp_path)
        os.replace(tmp_path, MODEL_PATH)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _prepare(data):
    X = np.asarray(data["X"], dtype=float)
    y_list = list(data["y"])
    if X.ndim != 2 or len(X) == 0 or len(X) != len(y_list):
        raise ValueError("model arrays are inconsistent")
    groups = {}
    for i, sid in enumerate(y_list):
        groups.setdefault(sid, []).append(i)
    return {
        "clf": data["clf"],
        "X_np": X,
        "y_list": y_list,
        "groups": {sid: np.array(idx) for sid, idx in groups.items()},
    }


def load_model():
    """Return the prepared model, reloading only when the file changed.
    Returns None if missing or unreadable."""
    try:
        st = os.stat(MODEL_PATH)
    except FileNotFoundError:
        return None
    sig = (st.st_mtime_ns, st.st_size)
    with _cache_lock:
        if _cache["sig"] == sig and _cache["model"] is not None:
            return _cache["model"]
    try:
        model = _prepare(joblib.load(MODEL_PATH))
    except Exception:
        log.exception("model.pkl could not be loaded")
        return None
    with _cache_lock:
        _cache["sig"], _cache["model"] = sig, model
    return model
