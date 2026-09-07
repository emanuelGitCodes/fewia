"""Test locked lease heartbeat, sticky loss, and thread join."""

import math
import threading
from types import TracebackType
from typing import Self

import pytest

from app.services.heartbeat import Heartbeat
from app.services.job_delivery import LeaseLost, RetryableJobError


def _alive_heartbeats() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name == "job-heartbeat" and thread.is_alive()
    ]


class _ContendedLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.waiting = threading.Event()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if self._lock.acquire(blocking=False):
            return True
        self.waiting.set()
        if not blocking:
            return False
        return self._lock.acquire(blocking, timeout)

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> Self:
        acquired = self.acquire()
        if not acquired:
            raise RuntimeError("lock acquire failed")
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.release()


@pytest.mark.parametrize("interval", [0, -1.0, math.nan, math.inf, "15"])
def test_interval_must_be_finite_and_positive(interval: object) -> None:
    with pytest.raises(ValueError):

        def renew() -> None:
            return None

        Heartbeat(renew, interval_seconds=interval)  # type: ignore[arg-type]


def test_background_renews_several_times_while_handler_runs() -> None:
    count = 0
    lock = threading.Lock()
    enough = threading.Event()

    def renew() -> None:
        nonlocal count
        with lock:
            count += 1
            if count >= 4:
                enough.set()

    with Heartbeat(renew, interval_seconds=0.02):
        assert enough.wait(timeout=2)
    assert count >= 4
    assert _alive_heartbeats() == []


def test_manual_and_background_renewals_do_not_overlap() -> None:
    current = 0
    maximum = 0
    calls = 0
    state = threading.Lock()
    second = threading.Event()
    release = threading.Event()
    contended = _ContendedLock()
    worker: threading.Thread | None = None

    def renew() -> None:
        nonlocal current, maximum, calls
        with state:
            calls += 1
            current += 1
            maximum = max(maximum, current)
            n = calls
        if n >= 2:
            second.set()
            assert release.wait(timeout=2)
        with state:
            current -= 1

    pulse_ctx = Heartbeat(renew, interval_seconds=0.02)
    pulse_ctx._lock = contended
    try:
        with pulse_ctx as pulse:
            try:
                assert second.wait(timeout=2)
                worker = threading.Thread(target=pulse)
                worker.start()
                assert contended.waiting.wait(timeout=2)
                release.set()
                worker.join(timeout=2)
                assert not worker.is_alive()
            finally:
                release.set()
                if worker is not None:
                    worker.join(timeout=2)
    finally:
        pulse_ctx._stop.set()
        thread = pulse_ctx._thread
        if thread is not None:
            thread.join(timeout=2)
    assert maximum == 1
    assert _alive_heartbeats() == []


def test_late_blocked_background_failure_raises_after_handler_returns() -> None:
    calls = 0
    in_second = threading.Event()
    handler_done = threading.Event()

    def renew() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        in_second.set()
        assert handler_done.wait(timeout=2)
        raise RuntimeError("late failure")

    with pytest.raises(LeaseLost) as raised:
        with Heartbeat(renew, interval_seconds=0.02):
            assert in_second.wait(timeout=2)
            handler_done.set()
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert _alive_heartbeats() == []


def test_swallowed_manual_failure_is_sticky_and_skips_later_renewals() -> None:
    calls = 0

    def renew() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        raise RuntimeError("secret-token")

    with pytest.raises(LeaseLost) as raised:
        with Heartbeat(renew, interval_seconds=60) as pulse:
            with pytest.raises(LeaseLost) as first:
                pulse()
            assert first.value.__cause__ is None
            with pytest.raises(LeaseLost):
                pulse()
            assert calls == 2
    assert raised.value.__cause__ is None
    assert "secret-token" not in str(raised.value)
    assert _alive_heartbeats() == []


def test_retryable_handler_error_becomes_lease_lost_after_background_loss() -> None:
    calls = 0
    failed = threading.Event()

    def renew() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        failed.set()
        raise RuntimeError("provider payload")

    with pytest.raises(LeaseLost) as raised:
        with Heartbeat(renew, interval_seconds=0.02):
            assert failed.wait(timeout=2)
            raise RetryableJobError("retry")
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert _alive_heartbeats() == []


def test_thread_joins_on_success_handler_error_and_loss() -> None:
    def ok() -> None:
        return None

    with Heartbeat(ok, interval_seconds=60):
        pass
    assert _alive_heartbeats() == []

    with pytest.raises(RuntimeError, match="handler"):
        with Heartbeat(ok, interval_seconds=60):
            raise RuntimeError("handler")
    assert _alive_heartbeats() == []

    calls = 0

    def fail_second() -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("lost")

    with pytest.raises(LeaseLost):
        with Heartbeat(fail_second, interval_seconds=60) as pulse:
            with pytest.raises(LeaseLost):
                pulse()
    assert _alive_heartbeats() == []
    frozen = calls
    assert frozen == 2


def test_waiting_renewal_does_not_start_after_stop() -> None:
    calls = 0
    contended = _ContendedLock()
    stopper: threading.Thread | None = None
    held = False

    def renew() -> None:
        nonlocal calls
        calls += 1

    pulse_ctx = Heartbeat(renew, interval_seconds=0.02)
    pulse_ctx._lock = contended
    try:
        pulse_ctx.__enter__()
        assert calls == 1
        contended.acquire()
        held = True
        assert contended.waiting.wait(timeout=2)
        stopper = threading.Thread(target=pulse_ctx.__exit__, args=(None, None, None))
        stopper.start()
        assert pulse_ctx._stop.wait(timeout=2)
        contended.release()
        held = False
        stopper.join(timeout=2)
        assert not stopper.is_alive()
        assert calls == 1
    finally:
        pulse_ctx._stop.set()
        if held:
            contended.release()
        thread = pulse_ctx._thread
        if thread is not None:
            thread.join(timeout=2)
        if stopper is not None:
            stopper.join(timeout=2)
    assert _alive_heartbeats() == []


def test_initial_failure_does_not_start_a_thread() -> None:
    def renew() -> None:
        raise RuntimeError("denied")

    with pytest.raises(LeaseLost) as raised:
        with Heartbeat(renew, interval_seconds=0.02):
            raise AssertionError("handler must not run")
    assert raised.value.__cause__ is None
    assert _alive_heartbeats() == []


def test_handler_error_is_preserved_when_the_lease_is_held() -> None:
    def renew() -> None:
        return None

    with pytest.raises(ValueError, match="handler"):
        with Heartbeat(renew, interval_seconds=60):
            raise ValueError("handler")
    assert _alive_heartbeats() == []
