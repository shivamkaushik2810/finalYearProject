import os
import threading
import time

import pytest

from src.services.load_balancer import BalancedRunner, default_workers, configured_workers


@pytest.fixture
def runner():
    r = BalancedRunner(workers=4, max_in_flight=6)
    yield r
    r.close()


def test_empty_batch(runner):
    assert runner.run(lambda x: x, []) == []


def test_single_task(runner):
    res = runner.run(lambda x: x + 1, [41])
    assert len(res) == 1 and res[0].ok and res[0].value == 42


def test_order_preserved_when_earlier_item_is_slow(runner):
    def f(x):
        if x == 0:
            time.sleep(0.05)
        return x * 10

    results = runner.run(f, range(8))
    assert [r.index for r in results] == list(range(8))
    assert [r.value for r in results] == [x * 10 for x in range(8)]


def test_repeated_runs_on_same_runner(runner):
    for _ in range(3):
        res = runner.run(lambda x: x, range(5))
        assert [r.value for r in res] == list(range(5))


def test_failure_isolated_and_type_reported(runner):
    def f(x):
        if x == 1:
            raise ValueError("unreadable image")
        return x

    res = runner.run(f, [0, 1, 2])
    assert [r.ok for r in res] == [True, False, True]
    assert res[1].value is None
    assert res[1].error == "ValueError"
    assert res[0].value == 0 and res[2].value == 2


def test_no_slot_leak_after_failures(runner):
    def boom(x):
        raise RuntimeError("x")

    runner.run(boom, range(10))
    res = runner.run(lambda x: x, range(10))  # would hang or fail if slots leaked
    assert all(r.ok for r in res)


def test_in_flight_bound_respected():
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def f(x):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.01)
        with lock:
            state["now"] -= 1
        return x

    r = BalancedRunner(workers=4, max_in_flight=2)
    try:
        res = r.run(f, range(20))
    finally:
        r.close()
    assert len(res) == 20 and all(t.ok for t in res)
    assert state["peak"] <= 2


def test_concurrent_callers_are_safe():
    r = BalancedRunner(workers=2, max_in_flight=4)
    errors = []

    def caller(offset):
        try:
            res = r.run(lambda x: x + offset, range(10))
            assert [t.value for t in res] == [x + offset for x in range(10)]
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=caller, args=(i,)) for i in range(4)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    finally:
        r.close()
    assert not errors


def test_close_is_idempotent():
    r = BalancedRunner(workers=1, max_in_flight=1)
    r.close()
    r.close()  # must not raise


def test_submit_after_close_fails_clearly():
    r = BalancedRunner(workers=1, max_in_flight=1)
    r.close()
    with pytest.raises(RuntimeError, match="closed"):
        r.run(lambda x: x, [1])


def test_default_workers_caps_at_two():
    assert default_workers(cpu_count=1) == 1
    assert default_workers(cpu_count=8) == 2


def test_default_workers_uses_machine_count(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert default_workers(cpu_count=None) == 2


def test_default_workers_when_cpu_unknown(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert default_workers(cpu_count=None) == 1


@pytest.mark.parametrize("raw", ["abc", "0", "-3", ""])
def test_invalid_env_falls_back(monkeypatch, raw):
    monkeypatch.setenv("SNAPCLASS_MAX_WORKERS", raw)
    assert configured_workers() == default_workers()


@pytest.mark.parametrize("invalid_value", [0, -1, -5])
def test_invalid_max_in_flight_raises_value_error(invalid_value):
    with pytest.raises(
        ValueError,
        match="max_in_flight must be at least 1",
    ):
        BalancedRunner(workers=3, max_in_flight=invalid_value)
