import json
import sys
import threading
import time
from pathlib import Path

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
            'print(\'{"type":"error","code":"insufficient_quota"}\'); raise SystemExit(1)',
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
    (tmp_path / "confirm-stall").write_text("unique")
    script = 'import time; print(\'{"type":"item.started","item":{"type":"command_execution","id":"x"}}\', flush=True); time.sleep(2)'
    assert run(tmp_path, script, idle=0.02, limit=0.15) == "time_limit"
    assert json.loads((tmp_path / "status.json").read_text())["active_tools"]


def test_permission_does_not_fall_back(tmp_path: Path) -> None:
    assert run(tmp_path, 'print(\'{"type":"permission_request"}\')') == "permission"


def test_child_is_stopped_before_return(tmp_path: Path) -> None:
    script = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', \"import time; from pathlib import Path; time.sleep(1); Path('late').touch()\"]); time.sleep(3)"
    result = run(tmp_path, script, idle=0.02, limit=0.15)
    assert result in {"time_limit", "cleanup_failed"}
    time.sleep(1)
    assert not (tmp_path / "late").exists()
