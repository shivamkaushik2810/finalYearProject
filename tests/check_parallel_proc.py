"""Sequential vs multi-process face scan. Usage: python tests/check_parallel_proc.py PHOTO_DIR"""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    import numpy as np
    from PIL import Image
    from src.pipelines.face_pipeline import predict_attendance_with_encodings
    from src.pipelines.face_parallel import predict_many
    from src.services import adaptive_balancer as lb

    folder = Path(sys.argv[1])
    imgs = [np.array(Image.open(p).convert("RGB")) for p in sorted(folder.iterdir())
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not imgs:
        sys.exit("No images found.")
    cpus = os.cpu_count() or 1
    print(f"images: {len(imgs)}  status: {lb.get_status()}")

    predict_many(imgs[:cpus])  # warm-up: starts workers and loads dlib models in each
    t0 = time.perf_counter()
    seq = [frozenset(predict_attendance_with_encodings(a)[0].keys()) for a in imgs]
    seq_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    par = predict_many(imgs)
    par_t = time.perf_counter() - t0
    failed = sum(r is None for r in par)
    same = all(r is not None and frozenset(r[0].keys()) == s for r, s in zip(par, seq))

    speedup = seq_t / par_t if par_t else 0
    print(f"sequential: {seq_t:6.2f}s   multi-process: {par_t:6.2f}s   speedup x{speedup:.2f}")
    print(f"results identical: {same}   failed photos: {failed}")
    ok = same and failed == 0 and (speedup >= 1.3 or cpus <= 2)
    print("VERDICT:", "PARALLEL WORKING (real speedup)" if ok else "NOT OK - see numbers above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":  # required: worker processes re-import this file
    main()
