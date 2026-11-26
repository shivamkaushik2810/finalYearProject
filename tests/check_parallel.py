"""Checks that parallel processing really happens and results match sequential.
Usage (project root):  python tests/check_parallel.py PHOTO_DIR
        no photos?     python tests/check_parallel.py --fake
"""
import hashlib, os, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
# face_pipeline reads this at import: without it only 2 scans run at once
os.environ.setdefault("SCAN_CONCURRENCY", str(os.cpu_count() or 1))

from src.services import adaptive_balancer as lb

args = [a for a in sys.argv[1:] if not a.startswith("--")]
FAKE = "--fake" in sys.argv


def fake_scan(_):
    hashlib.pbkdf2_hmac("sha256", b"x" * 64, b"salt", 300000)  # CPU work, releases the GIL
    return frozenset({1, 2})


def load_scan():
    import numpy as np
    from PIL import Image
    from src.pipelines.face_pipeline import predict_attendance_with_encodings
    folder = Path(args[0])
    imgs = [np.array(Image.open(p).convert("RGB")) for p in sorted(folder.iterdir())
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not imgs:
        sys.exit("No images found.")
    return imgs, lambda a: frozenset(predict_attendance_with_encodings(a)[0].keys())


if FAKE:
    items, scan = list(range(16)), fake_scan
else:
    if not args:
        sys.exit(__doc__)
    items, scan = load_scan()
    scan(items[0])  # warm-up: model + known-face cache

# 1. sequential baseline
c0, t0 = time.process_time(), time.perf_counter()
seq = [scan(i) for i in items]
seq_wall, seq_cpu = time.perf_counter() - t0, time.process_time() - c0

# 2. balanced run, recording who ran what and when
spans, lock = [], threading.Lock()


def traced(i):
    s = time.perf_counter()
    r = scan(i)
    with lock:
        spans.append((s, time.perf_counter(), threading.current_thread().name))
    return r


c0, t0 = time.process_time(), time.perf_counter()
par = lb.run_balanced(traced, items)
par_wall, par_cpu = time.perf_counter() - t0, time.process_time() - c0

events = sorted([(s, 1) for s, _, _ in spans] + [(e, -1) for _, e, _ in spans])
cur = peak = 0
for _, d in events:
    cur += d
    peak = max(peak, cur)

threads = sorted({n for _, _, n in spans})
cpu_ratio = par_cpu / par_wall if par_wall else 0
print(f"images: {len(items)}   status: {lb.get_status()}")
print(f"sequential : {seq_wall:6.2f}s  (cpu/wall {seq_cpu / seq_wall:.2f})")
print(f"balanced   : {par_wall:6.2f}s  (cpu/wall {cpu_ratio:.2f})   speedup x{seq_wall / par_wall:.2f}")
print(f"threads used: {len(threads)}  peak simultaneous tasks: {peak}")
print(f"results identical to sequential: {par == seq}   failed tasks: {sum(r is None for r in par)}")
ok = par == seq and peak > 1 and len(threads) > 1
print("VERDICT:", "PARALLEL WORKING" if ok else "NOT PARALLEL (see hints below)")
if peak <= 2 and (os.cpu_count() or 1) > 2:
    print("hint: peak is capped near 2 -> check SCAN_CONCURRENCY / SNAPCLASS_MAX_WORKERS")
if peak > 1 and cpu_ratio < 1.3 and (os.cpu_count() or 1) > 1:
    print("hint: tasks overlap but CPU is not above 1 core -> work is mostly waiting (DB/GIL), "
          "not using extra cores")
sys.exit(0 if ok else 1)
