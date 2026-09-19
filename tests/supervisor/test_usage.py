import json
import stat
from pathlib import Path

import pytest

from dev_supervisor.usage import (
    COUNTS,
    LEDGER,
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
        "gpt-5.6-luna",
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
