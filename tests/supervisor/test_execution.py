import json
from pathlib import Path
from unittest.mock import patch

from dev_supervisor.__main__ import execute
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
            assert f"Write({progress})" in args
            assert f"Edit({progress})" in args
            assert f"Write({owned})" in args
            assert f"Edit({owned})" in args
            assert args[args.index("--permission-mode") + 1] == "default"
        else:
            assert not any(arg.startswith("Write(") for arg in args)
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
                [owned],
            )
            == "completed"
        )
    assert seen == ["grok-4.6", "gpt-5.3-codex-spark"]


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
                    order("gpt-5.6-sol", False, MODELS),
                    1,
                    2,
                )
                == outcome
            )
            assert runner.call_count == 1
            assert "gpt-5.6-sol" in runner.call_args.args[0]
    with patch("dev_supervisor.__main__.attempt", return_value="quota") as runner:
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order("gpt-5.6-sol", True, MODELS),
                1,
                2,
            )
            == "all_providers_exhausted"
        )
        assert runner.call_count == 1
    assert (
        json.loads((tmp_path / "result.json").read_text())[0]["model"] == "gpt-5.6-sol"
    )


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
            )
            == "completed"
        )
    results = json.loads((tmp_path / "result.json").read_text())
    assert [row["outcome"] for row in results] == ["quota", "completed"]
