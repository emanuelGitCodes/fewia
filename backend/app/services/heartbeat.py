from __future__ import annotations

import math
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Literal

from app.services.job_delivery import LeaseLost


class Heartbeat:
    def __init__(
        self, renew: Callable[[], None], *, interval_seconds: float = 15
    ) -> None:
        try:
            valid = math.isfinite(interval_seconds) and interval_seconds > 0
        except TypeError:
            valid = False
        if not valid:
            raise ValueError("interval_seconds must be a finite positive number")
        self._renew = renew
        self._interval = interval_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._lost = False
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Callable[[], None]:
        self._call()
        if self._lost:
            raise LeaseLost from None
        self._thread = threading.Thread(
            target=self._loop, name="job-heartbeat", daemon=False
        )
        self._thread.start()
        return self._manual

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> Literal[False]:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join()
        if self._lost:
            raise LeaseLost from None
        return False

    def _manual(self) -> None:
        self._call()
        if self._lost:
            raise LeaseLost from None

    def _call(self) -> None:
        with self._lock:
            if self._stop.is_set() or self._lost:
                return
            try:
                self._renew()
            except Exception:  # noqa: BLE001
                self._lost = True
                self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._call()
