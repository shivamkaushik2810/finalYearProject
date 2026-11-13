"""Benchmark SnapClass face scanning: sequential vs BalancedRunner.

Usage (from project root):
  SCAN_CONCURRENCY=2 python scripts/benchmark_scan.py PHOTO_DIR --workers 2 --reps 3

--workers 0 = sequential. Use only test photos you are allowed to use.
Output contains timings, counts and match/mismatch totals. No IDs are printed or saved.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SUPPORTED = {".jpg", ".jpeg", ".png"}


def fail(msg: str):
    sys.exit(f"ERROR: {msg}")


def rss_mb():
    """Current resident memory in MB, platform-aware. None if unavailable."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except ImportError:
        pass
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kilobytes.
        return peak / 1e6 if sys.platform == "darwin" else peak / 1e3
    except (ImportError, AttributeError):
        return None


def load_images(folder: Path):
    """Yield (name, RGB array) one at a time. Corrupt files are reported and skipped."""
    import numpy as np
    from PIL import Image
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in SUPPORTED:
            continue
        try:
            with Image.open(path) as im:
                yield path.name, np.array(im.convert("RGB"))
        except Exception as exc:
            print(f"  skipped unreadable image ({type(exc).__name__})")


def identities(arr):
    from src.pipelines.face_pipeline import predict_attendance_with_encodings
    detected, _, _, _ = predict_attendance_with_encodings(arr)
    return frozenset(detected.keys())


def run_sequential(images):
    out, times, errors = [], [], 0
    for _, arr in images:
        t0 = time.perf_counter()
        try:
            out.append(identities(arr))
        except Exception:
            errors += 1
            out.append(None)
        times.append(time.perf_counter() - t0)
    return out, times, errors


def run_parallel(images, workers, max_in_flight):
    from src.services.load_balancer import BalancedRunner
    runner = BalancedRunner(workers=workers, max_in_flight=max_in_flight)
    try:
        t0 = time.perf_counter()
        results = runner.run(lambda pair: identities(pair[1]), images)
        total = time.perf_counter() - t0
    finally:
        runner.close()
    out = [r.value if r.ok else None for r in results]
    errors = sum(1 for r in results if not r.ok)
    return out, total, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--workers", type=int, default=0, help="0 = sequential")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--max-in-flight", type=int, default=None)
    ap.add_argument("--json", type=Path, default=None, help="optional anonymised output file")
    args = ap.parse_args()

    if not args.folder.is_dir():
        fail(f"not a directory: {args.folder}")
    if args.workers < 0 or args.reps < 1:
        fail("--workers must be 0 or more, --reps at least 1")

    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        from src.pipelines import face_pipeline  # noqa: F401
    except ImportError as exc:
        fail(f"missing dependency: {exc.name}. Activate the project venv.")

    scan_conc = int(os.environ.get("SCAN_CONCURRENCY", "2"))
    if args.workers > scan_conc:
        fail(f"--workers {args.workers} exceeds SCAN_CONCURRENCY={scan_conc}. "
             f"Re-run with SCAN_CONCURRENCY={args.workers} or fewer workers.")

    # Cache must not refresh between runs, or sequential and parallel compare different data.
    os.environ.setdefault("KNOWN_FACES_TTL", "3600")

    images = list(load_images(args.folder))
    if not images:
        fail("no readable .jpg/.jpeg/.png images in that folder")

    baseline = rss_mb()
    identities(images[0][1])  # warm-up: model and known-face cache
    warm = rss_mb()

    seq_ids, seq_times, seq_errors = None, [], 0
    par_runs, par_errors = [], 0
    mode = "sequential" if args.workers == 0 else f"parallel-{args.workers}"
    max_in_flight = args.max_in_flight or args.workers * 2

    print("SnapClass Face Recognition Benchmark")
    print(f"  Mode: {mode}  Workers: {args.workers}  Max in-flight: {max_in_flight}")
    print(f"  Images: {len(images)}  Repetitions: {args.reps}  SCAN_CONCURRENCY: {scan_conc}")

    run_times, peak = [], warm
    cpu_before = time.process_time()
    wall_before = time.perf_counter()
    for _ in range(args.reps):
        if args.workers == 0:
            ids, times, errs = run_sequential(images)
            run_times.append(sum(times))
            seq_times.extend(times)
            seq_ids, seq_errors = ids, errs
        else:
            ids, total, errs = run_parallel(images, args.workers, max_in_flight)
            run_times.append(total)
            par_runs.append(ids)
            par_errors = errs
        now = rss_mb()
        if now and (peak is None or now > peak):
            peak = now
    wall_total = time.perf_counter() - wall_before
    cpu_total = time.process_time() - cpu_before

    median_total = statistics.median(run_times)
    n = len(images)
    print("\nPerformance (median across repetitions)")
    print(f"  Total time: {median_total:.2f} s")
    print(f"  Average per image: {median_total / n:.3f} s")
    print(f"  Images per second: {n / median_total:.2f}")
    print(f"  CPU utilization: {cpu_total / wall_total:.2f}x")
    if args.workers == 0 and seq_times:
        s = sorted(seq_times)
        p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
        print(f"  Median latency: {statistics.median(s):.3f} s   P95 latency: {p95:.3f} s")
    print(f"  Baseline RAM: {baseline:.0f} MB" if baseline else "  Baseline RAM: unavailable")
    if peak and baseline:
        print(f"  Peak RAM: {peak:.0f} MB (+{peak - baseline:.0f} MB over baseline)")
    errors = seq_errors if args.workers == 0 else par_errors
    print(f"  Errors: {errors}")

    summary = {"mode": mode, "workers": args.workers, "max_in_flight": max_in_flight,
               "images": n, "reps": args.reps, "median_total_s": round(median_total, 3),
               "images_per_s": round(n / median_total, 3), "errors": errors,
               "baseline_rss_mb": baseline and round(baseline, 1),
               "peak_rss_mb": peak and round(peak, 1)}

    if args.workers > 0:
        # Sequential reference for consistency: one extra sequential pass.
        ref_ids, _, _ = run_sequential(images)
        mismatches = 0
        for run in par_runs:
            mismatches += sum(1 for a, b in zip(ref_ids, run) if a != b)
        compared = n * len(par_runs)
        print("\nConsistency (sequential vs parallel, identities compared internally)")
        print(f"  Comparisons: {compared}  Matching: {compared - mismatches}  Mismatched: {mismatches}")
        summary["consistency"] = {"comparisons": compared, "mismatched": mismatches}
    else:
        print("\nConsistency: not applicable to the sequential baseline.")

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nAnonymised summary written to {args.json}")


if __name__ == "__main__":
    main()