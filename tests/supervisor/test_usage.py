import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from dev_supervisor.__main__ import execute
from dev_supervisor.policy import MODELS, order
from dev_supervisor.usage import (
    COUNTS,
    LEDGER,
    phase_name,
    summarize,
    work_item_id,
    write_usage,
)
from tests.supervisor.test_execution import setup


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


def test_summary_groups_repairs_and_unknowns(tmp_path: Path) -> None:
    path = tmp_path / LEDGER
    write_usage(
        path, "a", "cap-1", "implement", "codex", "m", "low", "completed", _meta(2), 1
    )
    write_usage(
        path, "b", "cap-1", "repair", "codex", "m", "low", "completed", _meta(5), 1
    )
    write_usage(
        path,
        "c",
        "cap-1",
        "repair",
        "codex",
        "m",
        "low",
        "task_failed",
        {"provenance": "none"},
        1,
    )
    path.write_text(path.read_text() + "{not json}\n")
    summary = summarize(path)
    assert summary["excluded"] == ["astra", "native"]
    assert summary["tokens_are_not_money_or_quota"] is True
    group = summary["groups"][0]
    assert group["work_item"] == "cap-1"
    assert group["provider"] == "codex"
    assert group["attempts"] == 3
    assert group["repairs"] == 2
    assert group["input_tokens"] == 7
    assert group["input_tokens_unknown"] == 1
    assert group["known_token_totals_only"] is True
    assert summary["known_token_totals_are_not_spend"] is True
    write_usage(
        path, "d", "cap-2", "implement", "grok", "g", "low", "task_failed", _meta(8), 1
    )
    grok_group = next(
        item for item in summarize(path)["groups"] if item["provider"] == "grok"
    )
    assert grok_group["input_tokens"] is None
    assert grok_group["input_tokens_unknown"] == 1
    assert "cost" not in summary
    assert "quota" not in summary
    assert "spend" not in grok_group


def test_execute_records_failure_without_private_text(tmp_path: Path) -> None:
    task = setup(tmp_path)
    with patch("dev_supervisor.__main__.attempt", return_value="task_failed"):
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
                "standard",
                None,
                None,
                "cap-1",
                "implement",
            )
            == "task_failed"
        )
    row = json.loads((tmp_path / LEDGER).read_text().splitlines()[0])
    assert row["outcome"] == "task_failed"
    assert row["work_item"] == "cap-1"
    assert row["phase"] == "implement"
    assert row["provider"] == "codex"
    assert "Own only assigned files." not in (tmp_path / LEDGER).read_text()
    assert row["input_tokens"] is None


def test_execute_records_interrupt_launch_and_cleanup_without_raw_text(
    tmp_path: Path,
) -> None:
    task = setup(tmp_path)
    expected_returns = {
        "interrupted": "interrupted",
        "unavailable": "all_providers_exhausted",
        "cleanup_failed": "cleanup_failed",
    }
    for outcome in ("interrupted", "unavailable", "cleanup_failed"):
        with patch("dev_supervisor.__main__.attempt", return_value=outcome):
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
                    "standard",
                    None,
                    None,
                    "cap-1",
                    "implement",
                )
                == expected_returns[outcome]
            )
    text = (tmp_path / LEDGER).read_text()
    assert "Own only assigned files." not in text
    assert "credential" not in text
    outcomes = [json.loads(line)["outcome"] for line in text.splitlines()]
    assert outcomes == ["interrupted", "unavailable", "cleanup_failed"]
    for row in (json.loads(line) for line in text.splitlines()):
        assert row["input_tokens"] is None
        assert set(row) == {
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
