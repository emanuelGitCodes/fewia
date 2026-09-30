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


def test_codex_prompt_allows_readonly_shell(tmp_path: Path) -> None:
    task = setup(tmp_path)
    captured: list[str] = []

    def runner(
        args: list[str],
        cwd: Path,
        prompt: Path,
        state: Path,
        token: str,
        idle: float,
        limit: float,
    ) -> str:
        captured.append(prompt.read_text())
        return "completed"

    with patch("dev_supervisor.__main__.attempt", runner):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order("gpt-5.3-codex-spark", True, MODELS),
                1,
                2,
                "standard",
            )
            == "completed"
        )
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order("grok-4.6", True, MODELS),
                1,
                2,
                "standard",
            )
            == "completed"
        )
    codex_text, grok_text = captured
    assert (
        "You MAY run read-only shell commands to read and search files: cat, sed -n, "
        "head, tail, ls, rg, grep, and find. Edit files only with apply_patch. You "
        "MUST NOT run tests, package managers, git commands, or any command that "
        "writes, moves, or deletes a file."
    ) in " ".join(codex_text.split())
    assert (
        "You MUST NOT run shell commands, tests, package managers, or git commands."
        in grok_text
    )
    assert "You MAY run read-only shell commands" not in grok_text


def test_completed_without_owned_edits_is_no_edits_and_retries(
    tmp_path: Path,
) -> None:
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
        seen.append(args[args.index("--model") + 1])
        if len(seen) == 2:
            owned.write_text("changed\n")
        return "completed"

    with patch("dev_supervisor.__main__.attempt", runner):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                ["grok-4.6", "gpt-5.3-codex-spark"],
                1,
                2,
                "standard",
                None,
                [owned],
            )
            == "completed"
        )
    assert seen == ["grok-4.6", "gpt-5.3-codex-spark"]
    results = json.loads((tmp_path / "result.json").read_text())
    assert [row["outcome"] for row in results] == ["no_edits", "completed"]


def test_completed_with_owned_edits_stays_completed(tmp_path: Path) -> None:
    task = setup(tmp_path)
    owned = tmp_path / "owned.py"
    owned.write_text("pass\n")

    def runner(
        args: list[str],
        cwd: Path,
        prompt: Path,
        state: Path,
        token: str,
        idle: float,
        limit: float,
    ) -> str:
        owned.write_text("changed\n")
        return "completed"

    with patch("dev_supervisor.__main__.attempt", runner):
        assert (
            execute(
                tmp_path,
                task,
                "backend-dev",
                tmp_path,
                MODELS,
                order("grok-4.6", True, MODELS),
                1,
                2,
                "standard",
                None,
                [owned],
            )
            == "completed"
        )
    results = json.loads((tmp_path / "result.json").read_text())
    assert [row["outcome"] for row in results] == ["completed"]
