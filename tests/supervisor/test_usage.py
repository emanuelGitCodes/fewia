import json
import stat
import subprocess
from pathlib import Path

import pytest

from dev_supervisor.usage import (
    COUNTS,
    LEDGER,
    ledger_path,
    phase_name,
    work_item_id,
    write_usage,
)


def _meta(input_tokens: int = 2) -> dict[str, object]:
    return {
        "provenance": "codex.turn.completed",
        "input_tokens": input_tokens,
        "cached_tokens": 1,
        "output_tokens": 3,
        "reasoning_tokens": 4,
    }


def test_work_item_and_phase_validation() -> None:
    assert work_item_id("cap-1") == "cap-1"
    with pytest.raises(ValueError):
        work_item_id("../secret")
    with pytest.raises(ValueError):
        phase_name("done")


def test_write_usage_privacy_and_grok_null(tmp_path: Path) -> None:
    path = tmp_path / LEDGER
    write_usage(
        path,
        "a1",
        "cap-1",
        "implement",
        "codex",
        "gpt-6-luna",
        "medium",
        "completed",
        {**_meta(), "prompt": "SECRET", "error": "credential=abc"},
        9,
    )
    write_usage(
        path,
        "a2",
        "cap-1",
        "repair",
        "grok",
        "grok-4.6",
        "medium",
        "task_failed",
        _meta(8),
        4,
    )
    lines = path.read_text().splitlines()
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert "SECRET" not in path.read_text()
    assert "credential" not in path.read_text()
    assert first["input_tokens"] == 2
    assert first["coverage"] == "complete"
    assert second["input_tokens"] is None
    assert second["provenance"] == "unsupported"
    assert second["coverage"] == "unsupported"
    assert set(first) == {
        "id",
        "work_item",
        "phase",
        "provider",
        "model",
        "effort",
        "outcome",
        "elapsed_ms",
        *COUNTS,
        "provenance",
        "coverage",
    }


def test_write_usage_rejects_symlink_and_enforces_owner_mode(tmp_path: Path) -> None:
    target = tmp_path / "hidden.jsonl"
    target.write_text("keep\n")
    link = tmp_path / LEDGER
    link.symlink_to(target)
    with pytest.raises(OSError):
        write_usage(
            link,
            "a1",
            "cap-1",
            "implement",
            "codex",
            "m",
            "low",
            "completed",
            _meta(),
            1,
        )
    assert target.read_text() == "keep\n"
    path = tmp_path / "nested" / LEDGER
    write_usage(
        path, "a1", "cap-1", "implement", "codex", "m", "low", "completed", _meta(), 1
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o644)
    write_usage(
        path, "a2", "cap-1", "implement", "codex", "m", "low", "completed", _meta(), 1
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not path.is_symlink()


def _init_git(path: Path) -> Path:
    path.mkdir()
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "dev@example.test"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Dev"], cwd=path)
    subprocess.check_call(["git", "config", "commit.gpgsign", "false"], cwd=path)
    (path / "keep.txt").write_text("ok\n")
    subprocess.check_call(["git", "add", "keep.txt"], cwd=path)
    subprocess.check_call(
        ["git", "commit", "-m", "init"], cwd=path, stdout=subprocess.DEVNULL
    )
    return path


def _ledger_from_git(cwd: Path) -> Path:
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=cwd, text=True
    ).strip()
    root = Path(common)
    if not root.is_absolute():
        root = cwd / root
    return root.resolve() / LEDGER


def test_ledger_path_plain_repo(tmp_path: Path) -> None:
    repo = _init_git(tmp_path / "repo")
    assert ledger_path(repo) == _ledger_from_git(repo)


def test_ledger_path_linked_worktree(tmp_path: Path) -> None:
    main = _init_git(tmp_path / "main")
    linked = tmp_path / "linked"
    subprocess.check_call(
        ["git", "worktree", "add", "--detach", str(linked)],
        cwd=main,
        stdout=subprocess.DEVNULL,
    )
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=linked, text=True
    ).strip()
    root = Path(common)
    if not root.is_absolute():
        root = linked / root
    assert ledger_path(linked) == root.resolve() / LEDGER
    assert ledger_path(linked) == ledger_path(main)
    assert ledger_path(linked) != linked / LEDGER
