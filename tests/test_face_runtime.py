import threading
import time

from src.pipelines.face_runtime import FACE_RECOGNITION_LOCK


def test_face_recognition_lock_prevents_overlapping_operations():
    workers = 8
    barrier = threading.Barrier(workers)
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0

    def operation():
        nonlocal active, maximum_active
        barrier.wait(timeout=5)

        with FACE_RECOGNITION_LOCK:
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)

            time.sleep(0.01)

            with state_lock:
                active -= 1

    threads = [
        threading.Thread(target=operation)
        for _ in range(workers)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert maximum_active == 1


def test_face_recognition_lock_is_reentrant():
    with FACE_RECOGNITION_LOCK:
        with FACE_RECOGNITION_LOCK:
            assert True
