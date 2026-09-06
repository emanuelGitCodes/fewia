from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from dev_supervisor.events import Events


def stop(process: subprocess.Popen[bytes]) -> bool:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            process.wait()
            return True
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.05)
    return False


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
            return "unavailable"
        except PermissionError:
            return "permission"
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def interrupt(signum: int, frame: object) -> None:
            raise KeyboardInterrupt

        previous = signal.signal(signal.SIGTERM, interrupt)
        try:
            while True:
                now = time.monotonic()
                quiet = now - last >= idle
                status = {
                    "attempt": token,
                    "pid": process.pid,
                    "state": "needs_inspection" if quiet else "running",
                    "active_tools": bool(events.active_tools),
                    "permission_wait": events.waiting,
                }
                (state_dir / "status.json").write_text(json.dumps(status))
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
            signal.signal(signal.SIGTERM, previous)
            selector.close()
            clean = stop(process)
            process.stdout.close()
    return outcome if clean else "cleanup_failed"
