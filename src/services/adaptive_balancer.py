"""
Adaptive CPU load balancer for SnapClass.

- Pool size = all CPU threads (override: env SNAPCLASS_MAX_WORKERS).
- Automatic balancing: the number of tasks allowed to run at once shrinks
  when OTHER processes load the machine and grows back when it is idle.
- One process-wide limiter, so several teachers running attendance at the
  same time share the CPU instead of each grabbing every core.
- One failing item never breaks the others (its result is None).
"""
import logging
import os
import multiprocessing as mp
import threading
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool

log = logging.getLogger("snapclass.load_balancer")


def max_workers():
    raw = os.environ.get("SNAPCLASS_MAX_WORKERS")
    if raw:
        try:
            value = int(raw)
            if value >= 1:
                return value
        except ValueError:
            pass
        log.warning("Ignoring invalid SNAPCLASS_MAX_WORKERS value")
    return os.cpu_count() or 1


_MAX = max_workers()


def _load1():
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return None  # e.g. Windows: no load average -> use full capacity


def current_limit(active=0):
    """Allowed concurrent tasks right now (always >= 1)."""
    load = _load1()
    if load is None:
        return _MAX
    external = max(0.0, load - active)  # ignore the load we created ourselves
    return max(1, min(_MAX, _MAX - int(round(external))))


class _AdaptiveLimiter:
    def __init__(self):
        self._cond = threading.Condition()
        self._active = 0

    def acquire(self):
        with self._cond:
            while self._active >= current_limit(self._active):
                self._cond.wait(timeout=0.5)  # re-check load periodically
            self._active += 1

    def release(self):
        with self._cond:
            self._active -= 1
            self._cond.notify()

    @property
    def active(self):
        with self._cond:
            return self._active


_limiter = _AdaptiveLimiter()
_pool_lock = threading.Lock()
_pool = None


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=_MAX, thread_name_prefix="snapclass-worker"
            )
        return _pool


def _guarded(fn, item):
    _limiter.acquire()
    try:
        return fn(item)
    finally:
        _limiter.release()


def run_balanced(fn, items):
    """
    Run fn(item) for every item in parallel, load-balanced.
    Returns results in input order; a failed item gives None.
    Do NOT call Streamlit (st.*) inside fn - worker threads have no UI context.
    """
    items = list(items)
    if not items:
        return []
    pool = _get_pool()
    futures = [pool.submit(_guarded, fn, item) for item in items]
    results = []
    for index, future in enumerate(futures):
        try:
            results.append(future.result())
        except Exception:
            log.exception("Balanced task %d failed", index)
            results.append(None)
    return results


def get_status():
    return {
        "cpu_threads": os.cpu_count() or 1,
        "max_workers": _MAX,
        "allowed_now": current_limit(_limiter.active),
        "active": _limiter.active,
        "load_avg_1m": _load1(),
    }


# ---------------------------------------------------------------------------
# Process-based balancing: use this for CPU-bound work that holds the GIL
# (e.g. dlib face detection). fn and its items/results must be picklable, and
# fn must live in an importable module that does NOT import Streamlit/Supabase.
# ---------------------------------------------------------------------------
_proc_pool = None


def _get_proc_pool():
    global _proc_pool
    with _pool_lock:
        if _proc_pool is None:
            _proc_pool = ProcessPoolExecutor(max_workers=_MAX, mp_context=mp.get_context("spawn"))
        return _proc_pool


def _reset_proc_pool():
    global _proc_pool
    with _pool_lock:
        broken, _proc_pool = _proc_pool, None
    if broken is not None:
        broken.shutdown(wait=False, cancel_futures=True)


def run_balanced_processes(fn, items):
    """Like run_balanced but in worker processes. In-flight tasks follow current_limit()."""
    items = list(items)
    if not items:
        return []
    results = [None] * len(items)
    pending, nxt = {}, 0
    while nxt < len(items) or pending:
        limit = current_limit(len(pending))
        while nxt < len(items) and len(pending) < limit:
            try:
                pending[_get_proc_pool().submit(fn, items[nxt])] = nxt
            except Exception:
                log.exception("Could not submit task %d", nxt)
                _reset_proc_pool()
            nxt += 1
        if not pending:
            continue
        done, _ = wait(list(pending), timeout=0.5, return_when=FIRST_COMPLETED)
        for fut in done:
            index = pending.pop(fut)
            try:
                results[index] = fut.result()
            except BrokenProcessPool:
                log.error("Worker process died on task %d", index)
                _reset_proc_pool()
            except Exception:
                log.exception("Process task %d failed", index)
    return results
