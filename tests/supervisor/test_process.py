import json
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

from dev_supervisor.lease import lease
from dev_supervisor.process import attempt


def run(tmp_path: Path, script: str, **kwargs: float) -> str:
    prompt = tmp_path / "prompt"
    prompt.write_text("task")
    return attempt(
        [sys.executable, "-c", script], tmp_path, prompt, tmp_path, "unique", **kwargs
    )


def test_missing_and_failed(tmp_path: Path) -> None:
    assert run(tmp_path, "raise SystemExit(1)") == "task_failed"
    assert run(tmp_path, "print('quota_exceeded')") == "task_failed"
    assert (
        run(
            tmp_path,
            'print(\'{"type":"error","code":"insufficient_quota"}\'); '
            "raise SystemExit(1)",
        )
        == "quota"
    )


def test_silence_alone_never_falls_back(tmp_path: Path) -> None:
    assert (
        run(tmp_path, "import time; time.sleep(2)", idle=0.02, limit=0.15)
        == "time_limit"
    )


def test_confirmed_stall(tmp_path: Path) -> None:
    def confirm() -> None:
        time.sleep(0.15)
        (tmp_path / "confirm-stall").write_text("unique")

    thread = threading.Thread(target=confirm)
    thread.start()
    assert run(tmp_path, "import time; time.sleep(3)", idle=0.02, limit=1) == "stalled"
    thread.join()


def test_active_tool_cannot_be_declared_stalled(tmp_path: Path) -> None:
    written: list[bool] = []

    def confirm() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status_path = tmp_path / "status.json"
            if status_path.exists():
                status = json.loads(status_path.read_text())
                if status.get("state") == "needs_inspection" and status.get(
                    "active_tools"
                ):
                    (tmp_path / "confirm-stall").write_text("unique")
                    written.append(True)
                    return
            time.sleep(0.01)

    script = (
        "import time; print("
        '\'{"type":"item.started","item":{"type":"command_execution","id":"x"}}\', '
        "flush=True); time.sleep(5)"
    )
    thread = threading.Thread(target=confirm)
    thread.start()
    assert run(tmp_path, script, idle=0.02, limit=1.5) == "time_limit"
    thread.join()
    assert written == [True]
    assert not (tmp_path / "confirm-stall").exists()
    assert json.loads((tmp_path / "status.json").read_text())["active_tools"]


def test_permission_does_not_fall_back(tmp_path: Path) -> None:
    assert run(tmp_path, 'print(\'{"type":"permission_request"}\')') == "permission"


def test_child_is_stopped_before_return(tmp_path: Path) -> None:
    script = (
        "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', "
        '"import time; from pathlib import Path; time.sleep(1); '
        "Path('late').touch()\"]); time.sleep(3)"
    )
    result = run(tmp_path, script, idle=0.02, limit=0.15)
    assert result in {"time_limit", "cleanup_failed"}
    time.sleep(1)
    assert not (tmp_path / "late").exists()
    status = json.loads((tmp_path / "status.json").read_text())["state"]
    assert status == ("stopped" if result == "time_limit" else status)


def test_launching_marker_before_popen(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt"
    prompt.write_text("task")
    seen: list[str] = []

    def boom(*args: object, **kwargs: object) -> None:
        seen.append(json.loads((tmp_path / "status.json").read_text())["state"])
        raise FileNotFoundError("missing")

    with patch("dev_supervisor.process.subprocess.Popen", boom):
        assert (
            attempt(["missing"], tmp_path, prompt, tmp_path, "token") == "unavailable"
        )
    assert seen == ["launching"]
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "stopped"


def test_selector_setup_failure_stops_child(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt"
    prompt.write_text("task")
    children: list[subprocess.Popen[bytes]] = []
    real = subprocess.Popen

    def capture(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child = real(*args, **kwargs)
        children.append(child)
        return child

    try:
        with lease(tmp_path) as state:
            with (
                patch("dev_supervisor.process.subprocess.Popen", side_effect=capture),
                patch(
                    "dev_supervisor.process.selectors.DefaultSelector",
                    side_effect=OSError("selector allocation failed"),
                ),
            ):
                try:
                    attempt(
                        [sys.executable, "-c", "import time; time.sleep(30)"],
                        tmp_path,
                        prompt,
                        state,
                        "test",
                    )
                except OSError:
                    pass
            assert children[0].poll() is not None
            assert json.loads((state / "status.json").read_text())["state"] == "stopped"
        with lease(tmp_path):
            assert children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            if child.stdout is not None:
                child.stdout.close()


def _reap(children: list[subprocess.Popen[bytes]]) -> None:
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        if child.stdout is not None:
            child.stdout.close()


def test_selector_close_error_still_stops_child(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt"
    prompt.write_text("task")
    children: list[subprocess.Popen[bytes]] = []
    real = subprocess.Popen
    selector_factory = selectors.DefaultSelector

    def capture(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child = real(*args, **kwargs)
        children.append(child)
        return child

    def broken_close_factory() -> selectors.BaseSelector:
        selector = selector_factory()
        real_close = selector.close

        def broken_close() -> None:
            real_close()
            raise OSError("selector close failed")

        selector.close = broken_close
        return selector

    try:
        with (
            patch("dev_supervisor.process.subprocess.Popen", side_effect=capture),
            patch(
                "dev_supervisor.process.selectors.DefaultSelector",
                side_effect=broken_close_factory,
            ),
        ):
            result = attempt(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                tmp_path,
                prompt,
                tmp_path,
                "test",
                limit=0.1,
            )
        assert result == "time_limit"
        assert children[0].poll() is not None
        assert json.loads((tmp_path / "status.json").read_text())["state"] == "stopped"
    finally:
        _reap(children)


def test_non_main_thread_attempt_still_stops_child(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt"
    prompt.write_text("task")
    children: list[subprocess.Popen[bytes]] = []
    errors: list[str] = []
    outcome: list[str] = []
    real = subprocess.Popen

    def capture(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child = real(*args, **kwargs)
        children.append(child)
        return child

    def run() -> None:
        try:
            outcome.append(
                attempt(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    tmp_path,
                    prompt,
                    tmp_path,
                    "test",
                    limit=0.1,
                )
            )
        except (OSError, ValueError) as error:
            errors.append(f"{type(error).__name__}: {error}")

    try:
        with patch("dev_supervisor.process.subprocess.Popen", side_effect=capture):
            thread = threading.Thread(target=run)
            thread.start()
            thread.join()
        assert errors == []
        assert outcome == ["time_limit"]
        assert children[0].poll() is not None
        assert json.loads((tmp_path / "status.json").read_text())["state"] == "stopped"
    finally:
        _reap(children)
