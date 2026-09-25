import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dev_supervisor.__main__ import GUARD, dispatch, execute, main
from dev_supervisor.lease import lease
from dev_supervisor.policy import MODELS, order


def setup(tmp_path: Path) -> Path:
    roles = tmp_path / ".codex/agents"
    roles.mkdir(parents=True)
    (roles / "backend-dev.toml").write_text(
        'developer_instructions = "Own only assigned files."'
    )
    task = tmp_path / "task"
    task.write_text("Implement the assigned change.")
    return task


def test_fallback_keeps_worktree_and_checkpoint(tmp_path: Path) -> None:
    task = setup(tmp_path)
    owned = tmp_path / "owned.py"
    owned.write_text("pass\n")
    seen: list[str] = []

    def runner(
        args: list[str],
        cwd: Path,
        prompt: Path,
        state: Path,
        token: str,
        idle: float,
        limit: float,
    ) -> str:
        assert cwd == tmp_path
        seen.append(args[args.index("--model") + 1])
        assert "Own only assigned files." in prompt.read_text()
        progress = str(state / "progress.md")
        if args[0].endswith("grok"):
            assert args[args.index("--reasoning-effort") + 1] == "medium"
            assert f"Write({progress})" in args
            assert f"Edit({progress})" in args
            assert f"Write({owned})" in args
            assert f"Edit({owned})" in args
            assert args[args.index("--permission-mode") + 1] == "default"
        else:
            assert not any(arg.startswith("Write(") for arg in args)
            assert not any("model_reasoning_effort" in arg for arg in args)
        if len(seen) == 1:
            (cwd / "partial.py").write_text("value = 1")
            (state / "progress.md").write_text("Check A passed. Check B remains.")
            return "quota"
        assert (cwd / "partial.py").exists()
        assert "Check A passed. Check B remains." in prompt.read_text()
        return "completed"

    with patch("dev_supervisor.__main__.attempt", runner):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS),
                1,
                2,
                "standard",
                None,
                [owned],
            )
            == "completed"
        )
    assert seen == ["grok-4.6", "gpt-5.3-codex-spark"]
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["complexity"] == "standard"
    assert checkpoint["effort"] == "CLI configured default"


def test_explicit_medium_execute_skips_spark(tmp_path: Path) -> None:
    task = setup(tmp_path)
    seen: list[str] = []

    def runner(
        args: list[str],
        cwd: Path,
        prompt: Path,
        state: Path,
        token: str,
        idle: float,
        limit: float,
    ) -> str:
        assert cwd == tmp_path
        seen.append(args[args.index("--model") + 1])
        return "unavailable"

    with patch("dev_supervisor.__main__.attempt", runner):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS, "medium"),
                1,
                2,
                "standard",
                "medium",
            )
            == "all_providers_exhausted"
        )
    assert seen == ["grok-4.6", "gpt-6-luna"]


def test_exhaustion_is_bounded(tmp_path: Path) -> None:
    task = setup(tmp_path)
    with patch("dev_supervisor.__main__.attempt", return_value="unavailable") as runner:
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS),
                1,
                2,
                "standard",
            )
            == "all_providers_exhausted"
        )
        assert runner.call_count == 3


def test_only_override_and_nonprovider_errors_stop(tmp_path: Path) -> None:
    task = setup(tmp_path)
    for outcome in ["permission", "task_failed", "cleanup_failed", "time_limit"]:
        with patch("dev_supervisor.__main__.attempt", return_value=outcome) as runner:
            assert (
                execute(
                    tmp_path,
                    task,
                    "backend-dev",
                    tmp_path,
                    MODELS,
                    order("gpt-6-sol", False, MODELS),
                    1,
                    2,
                    "complex",
                )
                == outcome
            )
            assert runner.call_count == 1
            assert "gpt-6-sol" in runner.call_args.args[0]
    with patch("dev_supervisor.__main__.attempt", return_value="quota") as runner:
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order("gpt-6-sol", True, MODELS),
                1,
                2,
                "maximum",
                "max",
            )
            == "all_providers_exhausted"
        )
        assert runner.call_count == 1
    assert json.loads((tmp_path / "result.json").read_text())[0]["model"] == "gpt-6-sol"
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["complexity"] == "maximum"
    assert checkpoint["effort"] == "max"


def test_real_subprocess_handoff(tmp_path: Path) -> None:
    import sys

    task = setup(tmp_path)
    scripts = iter(
        [
            'from pathlib import Path; Path(\'edit.txt\').write_text(\'kept\'); print(\'{"type":"error","code":"quota_exceeded"}\'); raise SystemExit(1)',
            "from pathlib import Path; assert Path('edit.txt').read_text() == 'kept'; print('{\"type\":\"turn.completed\"}')",
        ]
    )
    with patch(
        "dev_supervisor.__main__.command",
        side_effect=lambda *args: [sys.executable, "-c", next(scripts)],
    ):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS),
                1,
                3,
                "simple",
            )
            == "completed"
        )
    results = json.loads((tmp_path / "result.json").read_text())
    assert [row["outcome"] for row in results] == ["quota", "completed"]


def _supervisor_paths(root: Path) -> list[Path]:
    return [
        path
        for path in root.iterdir()
        if path.name.startswith(".fewia-supervisor-")
        or path.name == "fewia-supervisor.lock"
    ]


def _state_dir(root: Path) -> Path:
    matches = [
        path
        for path in root.iterdir()
        if path.is_dir() and path.name.startswith(".fewia-supervisor-")
    ]
    assert len(matches) == 1
    return matches[0]


def _main_argv(tmp_path: Path, task: str, role: str) -> list[str]:
    return [
        "dev_supervisor",
        "--task",
        task,
        "--role",
        role,
        "--cwd",
        str(tmp_path),
        "--complexity",
        "standard",
    ]


def test_inline_task_exits_before_lease(tmp_path: Path) -> None:
    setup(tmp_path)
    with patch("sys.argv", _main_argv(tmp_path, "implement the change", "backend-dev")):
        with pytest.raises(SystemExit):
            main()
    assert _supervisor_paths(tmp_path) == []


def test_missing_role_exits_before_lease(tmp_path: Path) -> None:
    task = setup(tmp_path)
    with patch("sys.argv", _main_argv(tmp_path, str(task), "missing-role")):
        with pytest.raises(SystemExit):
            main()
    assert _supervisor_paths(tmp_path) == []


def test_prelaunch_failure_releases_lease(tmp_path: Path) -> None:
    task = setup(tmp_path)

    def boom(*args: object, **kwargs: object) -> str:
        raise Exception("prelaunch")

    with patch("dev_supervisor.__main__.execute", boom):
        with pytest.raises(Exception, match="prelaunch"):  # noqa: B017
            dispatch(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS),
                1,
                2,
                "standard",
            )
    status = json.loads((_state_dir(tmp_path) / "status.json").read_text())
    assert status["state"] == "stopped"
    with lease(tmp_path) as granted:
        assert granted.name.startswith(".fewia-supervisor-")


def test_existing_status_blocks_after_execute_failure(tmp_path: Path) -> None:
    task = setup(tmp_path)
    payload = {"pid": os.getpgrp(), "state": "running"}

    def write_then_fail(*args: object, **kwargs: object) -> str:
        state = args[3]
        assert isinstance(state, Path)
        (state / "status.json").write_text(json.dumps(payload))
        raise Exception("after launch")

    with patch("dev_supervisor.__main__.execute", write_then_fail):
        with pytest.raises(Exception, match="after launch"):  # noqa: B017
            dispatch(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order(None, False, MODELS),
                1,
                2,
                "standard",
            )
    status_path = _state_dir(tmp_path) / "status.json"
    assert json.loads(status_path.read_text()) == payload
    with pytest.raises(RuntimeError, match="Prior writer"), lease(tmp_path):
        pass


def test_guard_forbids_writer_commands() -> None:
    assert (
        "You MUST NOT run shell commands, tests, package managers, or git commands"
        in GUARD
    )
    assert "Never claim an unfinished check passed" not in GUARD
    assert "Record completed checks" not in GUARD
    assert "after each completed check" not in GUARD


def test_guard_overrides_role_check_instructions() -> None:
    assert (
        "This rule overrides any role or assignment text that asks you to run checks"
        in GUARD
    )
    assert "record the checks you would run as remaining work in progress.md" in GUARD
