"""
Read-only load test for SnapClass core paths.
Usage: python tests/load_test.py [path/to/face_photo.jpg]
Run from project root, against a TEST Supabase project.
"""
import sys, time, statistics
from concurrent.futures import ThreadPoolExecutor
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src.database.db import get_all_students

IMG = sys.argv[1] if len(sys.argv) > 1 else None
LEVELS = [1, 5, 10, 25, 50]
REQS_PER_WORKER = 3


def timed(fn):
    t = time.perf_counter()
    try:
        fn()
        return time.perf_counter() - t, None
    except Exception as e:
        return time.perf_counter() - t, repr(e)[:120]


def run(name, fn):
    print(f"\n== {name} ==")
    print(f"{'users':>5} {'reqs':>5} {'err':>4} {'p50(s)':>8} {'p95(s)':>8} {'req/s':>7}")
    for n in LEVELS:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(timed, fn) for _ in range(n * REQS_PER_WORKER)]
            res = [f.result() for f in futs]
        wall = time.perf_counter() - start
        lat = sorted(r[0] for r in res)
        errs = [r[1] for r in res if r[1]]
        p50 = statistics.median(lat)
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
        print(f"{n:>5} {len(res):>5} {len(errs):>4} {p50:>8.2f} {p95:>8.2f} {len(res)/wall:>7.2f}")
        if errs:
            print("   first error:", errs[0])
        if errs and len(errs) > len(res) * 0.2:
            print("   >20% errors, stopping this test"); break


run("DB read: get_all_students (used on every login/scan)", get_all_students)

if IMG:
    import numpy as np
    from PIL import Image
    from src.pipelines.face_pipeline import predict_attendance
    img = np.array(Image.open(IMG).convert("RGB"))
    run("Face scan: predict_attendance", lambda: predict_attendance(img))
else:
    print("\n(no image given: skipped face scan test)")
