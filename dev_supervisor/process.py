from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from dev_supervisor.events import Events
from dev_supervisor.usage import COUNTS


def publish(state_dir: Path, status: dict[str, Any]) -> None:
    handle, name = tempfile.mkstemp(prefix=".status-", dir=state_dir, text=True)
    try:
        with os.fdopen(handle, "w") as writer:
            writer.write(json.dumps(status))
            writer.flush()
            os.fsync(writer.fileno())
        Path(name).replace(state_dir / "status.json")
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise


def stop(process: subprocess.Popen[bytes]) -> bool:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        deadline = time.monotonic() + 2
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        while True:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                try:
                    process.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    return False
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))
    return False


def _write_usage(state_dir: Path, events: Events, started: float) -> None:
    elapsed = int((time.monotonic() - started) * 1000)
    totals = events.tokens
    payload: dict[str, Any] = {
        name: None if totals is None else totals[name] for name in COUNTS
    }
    payload["provenance"] = "none" if totals is None else events.provenance
    payload["elapsed_ms"] = elapsed
    (state_dir / "usage.json").write_text(json.dumps(payload))


def attempt(
    args: list[str],
    cwd: Path,
    prompt: Path,
    state_dir: Path,
    token: str,
    idle: float = 180,
    limit: float = 3600,
) -> str:
    events = Events()
    started = last = time.monotonic()
    pending = b""
    outcome = "task_failed"

    def snapshot(state: str, pid: int | None) -> dict[str, Any]:
        return {
            "attempt": token,
            "pid": pid,
            "state": state,
            "active_tools": bool(events.active_tools),
            "permission_wait": events.waiting,
        }

    publish(state_dir, snapshot("launching", None))
    with prompt.open("rb") as source:
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError:
            publish(state_dir, snapshot("stopped", None))
            return "unavailable"
        except PermissionError:
            publish(state_dir, snapshot("stopped", None))
            return "permission"
        selector: selectors.BaseSelector | None = None
        previous = signal.getsignal(signal.SIGTERM)
        installed = False
        clean = False
        try:
            publish(state_dir, snapshot("running", process.pid))
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)

            def interrupt(signum: int, frame: object) -> None:
                raise KeyboardInterrupt

            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGTERM, interrupt)
                installed = True
            while True:
                now = time.monotonic()
                quiet = now - last >= idle
                publish(
                    state_dir,
                    snapshot("needs_inspection" if quiet else "running", process.pid),
                )
                decision = state_dir / "confirm-stall"
                if decision.exists() and decision.read_text().strip() == token:
                    decision.unlink()
                    if quiet and not events.active_tools and not events.waiting:
                        outcome = "stalled"
                        break
                if now - started >= limit:
                    outcome = "time_limit"
                    break
                if events.waiting:
                    outcome = "permission"
                    break
                ready = selector.select(timeout=0.1)
                if ready:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if chunk:
                        last = time.monotonic()
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            events.feed(line.decode(errors="replace"))
                        if len(pending) > 1048576:
                            pending = b""
                    else:
                        selector.unregister(process.stdout)
                if process.poll() is not None and not selector.get_map():
                    if pending:
                        events.feed(pending.decode(errors="replace"))
                    outcome = events.outcome(process.returncode)
                    break
        finally:
            if installed:
                with suppress(Exception):
                    signal.signal(signal.SIGTERM, previous)
            if selector is not None:
                with suppress(Exception):
                    selector.close()
            try:
                clean = stop(process)
            except OSError:
                clean = False
            if process.stdout is not None:
                with suppress(Exception):
                    process.stdout.close()
            if clean:
                publish(state_dir, snapshot("stopped", process.pid))
            _write_usage(state_dir, events, started)
    return outcome if clean else "cleanup_failed"
