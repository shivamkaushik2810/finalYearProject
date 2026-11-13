"""Bounded, order-preserving parallel runner for CPU-heavy per-photo work.

Only pure computation may run in worker threads:
- No Streamlit calls
- No Supabase reads or writes
- No attendance inserts

A failed task produces TaskResult(ok=False).
A failed photo is never treated as present.
"""

from __future__ import annotations

import logging
import os
import threading

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, List, Optional, TypeVar

log = logging.getLogger("snapclass.load_balancer")

T = TypeVar("T")
R = TypeVar("R")

WORKER_CAP = 2


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    """Read a positive integer environment variable safely."""
    raw = os.environ.get(name)

    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw)
    except ValueError:
        log.warning(
            "Ignoring invalid %s; using %d",
            name,
            default,
        )
        return default

    if value < minimum:
        log.warning(
            "%s below %d; using %d",
            name,
            minimum,
            default,
        )
        return default

    return value


def default_workers(cpu_count: Optional[int] = None) -> int:
    """Return a conservative default worker count."""
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 1)

    return max(1, min(WORKER_CAP, cpus))


def configured_workers() -> int:
    """Get worker count from environment or safe default."""
    return _env_int(
        "SNAPCLASS_MAX_WORKERS",
        default_workers(),
    )


def configured_in_flight(workers: int) -> int:
    """Get maximum submitted-but-uncollected tasks."""
    return _env_int(
        "SNAPCLASS_MAX_IN_FLIGHT",
        workers * 2,
    )


@dataclass(frozen=True)
class TaskResult(Generic[R]):
    """Result of one task."""

    index: int
    ok: bool
    value: Optional[R] = None
    error: Optional[str] = None


class BalancedRunner:
    """Bounded, order-preserving thread-pool runner."""

    def __init__(
        self,
        workers: Optional[int] = None,
        max_in_flight: Optional[int] = None,
    ):
        self.workers = (
            workers
            if workers is not None
            else configured_workers()
        )

        if self.workers < 1:
            raise ValueError("workers must be at least 1")

        requested = (
            max_in_flight
            if max_in_flight is not None
            else configured_in_flight(self.workers)
        )

        if requested < 1:
            raise ValueError(
                "max_in_flight must be at least 1"
            )

        # Do not force this to be >= workers.
        # The user may intentionally choose a smaller limit.
        self.max_in_flight = requested

        self._pool = ThreadPoolExecutor(
            max_workers=self.workers,
            thread_name_prefix="snapclass-scan",
        )

        self._closed = False
        self._lock = threading.Lock()

    def run(
        self,
        fn: Callable[[T], R],
        items: Iterable[T],
    ) -> List[TaskResult[R]]:
        """Run tasks while preserving input order."""

        with self._lock:
            if self._closed:
                raise RuntimeError(
                    "BalancedRunner is closed"
                )

        results: List[Optional[TaskResult[R]]] = []
        window = deque()

        for index, item in enumerate(items):
            results.append(None)

            # Collect before submitting more work.
            if len(window) >= self.max_in_flight:
                self._collect(window, results)

            future = self._pool.submit(fn, item)
            window.append((index, future))

        while window:
            self._collect(window, results)

        return results  # type: ignore[return-value]

    @staticmethod
    def _collect(
        window: deque,
        results: list,
    ) -> None:
        """Collect one task without losing other task results."""

        index, future = window.popleft()

        try:
            value = future.result()

            results[index] = TaskResult(
                index=index,
                ok=True,
                value=value,
            )

        except Exception as exc:
            log.error(
                "Scan task %d failed: %s",
                index,
                type(exc).__name__,
            )

            results[index] = TaskResult(
                index=index,
                ok=False,
                value=None,
                error=type(exc).__name__,
            )

    def close(self) -> None:
        """Close the executor safely and wait for running tasks."""

        with self._lock:
            if self._closed:
                return

            self._closed = True

        self._pool.shutdown(
            wait=True,
            cancel_futures=True,
        )
