"""Shared synchronization for native face-recognition operations."""

import threading

# dlib/face_recognition native calls are serialized across application features.
FACE_RECOGNITION_LOCK = threading.RLock()
