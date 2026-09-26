import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from dev_supervisor.usage import (
    COUNTS,
    LEDGER,
    ledger_path,
    main,
    phase_name,
    summarize,
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


def test_usage_cli_summary_for_codex_and_grok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_git(tmp_path / "repo")
    path = ledger_path(repo)
    write_usage(
        path,
        "a1",
        "cap-1",
        "implement",
        "codex",
        "gpt-6-luna",
        "medium",
        "completed",
        _meta(),
        2000,
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
        4000,
    )
    monkeypatch.setattr(sys, "argv", ["usage", "--cwd", str(repo)])
    main()
    out = capsys.readouterr().out.splitlines()
    assert (
        "cap-1 implement runs=1 elapsed_s=2 input=2 output=3 coverage=complete" in out
    )
    assert (
        "cap-1 repair runs=1 elapsed_s=4 input=n/a output=n/a "
        "coverage=unsupported no_tokens=1" in out
    )
    monkeypatch.setattr(
        sys, "argv", ["usage", "--cwd", str(repo), "--work-item", "missing"]
    )
    main()
    assert capsys.readouterr().out == "No usage recorded.\n"


def _row(
    coverage: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    provenance: str = "none",
    elapsed_ms: int = 1000,
) -> dict[str, object]:
    return {
        "work_item": "cap-1",
        "phase": "implement",
        "elapsed_ms": elapsed_ms,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "provenance": provenance,
        "coverage": coverage,
    }


def test_summarize_mixed_grok_and_complete_codex() -> None:
    grok = _row("unsupported", provenance="unsupported", elapsed_ms=1000)
    codex = _row(
        "complete",
        input_tokens=2,
        cached_tokens=1,
        output_tokens=3,
        reasoning_tokens=4,
        provenance="codex.turn.completed",
        elapsed_ms=2000,
    )
    assert summarize([grok, codex]) == [
        "cap-1 implement runs=2 elapsed_s=3 input=2 output=3 coverage=partial no_tokens=1"
    ]


def test_summarize_all_grok_unsupported() -> None:
    grok = _row("unsupported", provenance="unsupported", elapsed_ms=2000)
    assert summarize([grok, grok]) == [
        "cap-1 implement runs=2 elapsed_s=4 input=n/a output=n/a "
        "coverage=unsupported no_tokens=2"
    ]


def test_summarize_all_complete_codex() -> None:
    first = _row(
        "complete",
        input_tokens=2,
        cached_tokens=1,
        output_tokens=3,
        reasoning_tokens=4,
        provenance="codex.turn.completed",
        elapsed_ms=2000,
    )
    second = _row(
        "complete",
        input_tokens=5,
        cached_tokens=1,
        output_tokens=7,
        reasoning_tokens=1,
        provenance="codex.turn.completed",
        elapsed_ms=1000,
    )
    assert summarize([first, second]) == [
        "cap-1 implement runs=2 elapsed_s=3 input=7 output=10 coverage=complete"
    ]


def test_summarize_no_counts_unknown() -> None:
    empty = _row("unknown", provenance="none", elapsed_ms=500)
    assert summarize([empty]) == [
        "cap-1 implement runs=1 elapsed_s=0.5 input=n/a output=n/a "
        "coverage=unknown no_tokens=1"
    ]


def test_summarize_ignores_stored_unsupported_when_counts_complete() -> None:
    row = _row(
        "unsupported",
        input_tokens=2,
        cached_tokens=1,
        output_tokens=3,
        reasoning_tokens=4,
        provenance="codex.turn.completed",
        elapsed_ms=1000,
    )
    assert summarize([row]) == [
        "cap-1 implement runs=1 elapsed_s=1 input=2 output=3 coverage=complete"
    ]


def test_summarize_ignores_stored_complete_when_provenance_unsupported() -> None:
    row = _row(
        "complete",
        input_tokens=2,
        cached_tokens=1,
        output_tokens=3,
        reasoning_tokens=4,
        provenance="unsupported",
        elapsed_ms=1000,
    )
    assert summarize([row]) == [
        "cap-1 implement runs=1 elapsed_s=1 input=2 output=3 coverage=unsupported"
    ]


def test_summarize_unreadable_shape_unknown() -> None:
    row: dict[str, object] = {
        "work_item": "cap-1",
        "phase": "implement",
        "elapsed_ms": 1000,
        "input_tokens": "2",
        "cached_tokens": "1",
        "output_tokens": "3",
        "reasoning_tokens": "4",
        "provenance": 12,
        "coverage": "complete",
    }
    assert summarize([row]) == [
        "cap-1 implement runs=1 elapsed_s=1 input=n/a output=n/a "
        "coverage=unknown no_tokens=1"
    ]


def test_usage_cli_no_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_git(tmp_path / "repo")
    monkeypatch.setattr(sys, "argv", ["usage", "--cwd", str(repo)])
    main()
    assert capsys.readouterr().out == "No usage recorded.\n"
