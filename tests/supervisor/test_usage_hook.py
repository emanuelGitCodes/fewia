import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
HOOK = REPOSITORY / ".claude/hooks/record-usage.sh"
FIXTURE = REPOSITORY / "tests/supervisor/fixtures/claude-transcript-session.jsonl"
LEDGER = ".fewia-supervisor-usage.jsonl"


def hook_environment(project: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(project)
    for name in ("FEWIA_WRITER", "FEWIA_HOOK_HOST"):
        environment.pop(name, None)
    return environment


def run_hook(
    payload: dict[str, object] | str, project: Path
) -> subprocess.CompletedProcess[str]:
    input_text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=input_text,
        env=hook_environment(project),
        capture_output=True,
        text=True,
        timeout=60,
    )


def initialize_project(project: Path) -> None:
    subprocess.run(
        ["git", "init", str(project)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def copy_transcript(project: Path) -> Path:
    transcript = project / FIXTURE.name
    shutil.copyfile(FIXTURE, transcript)
    return transcript


def read_ledger(project: Path) -> list[dict[str, object]]:
    ledger = project / ".git" / LEDGER
    return [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]


def test_subagent_stop_records_junior_usage(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    transcript = copy_transcript(tmp_path)

    result = run_hook(
        {
            "hook_event_name": "SubagentStop",
            "agent_transcript_path": str(transcript),
            "agent_type": "Explore",
        },
        tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    rows = read_ledger(tmp_path)
    assert len(rows) == 1
    assert rows[0]["phase"] == "junior"
    assert rows[0]["agent_type"] == "Explore"
    assert rows[0]["provider"] == "claude"


def test_stop_records_coordinate_usage(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    transcript = copy_transcript(tmp_path)

    result = run_hook(
        {"hook_event_name": "Stop", "transcript_path": str(transcript)}, tmp_path
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    rows = read_ledger(tmp_path)
    assert len(rows) == 1
    assert rows[0]["phase"] == "coordinate"
    assert rows[0]["agent_type"] is None


def test_repeated_stop_does_not_append_a_row(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    transcript = copy_transcript(tmp_path)
    payload = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

    first = run_hook(payload, tmp_path)
    second = run_hook(payload, tmp_path)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == ""
    assert first.stderr == second.stderr == ""
    assert len(read_ledger(tmp_path)) == 1


@pytest.mark.parametrize(
    "case",
    [
        "missing-path",
        "empty-path",
        "missing-file",
        "not-file",
        "unknown-event",
        "invalid-json",
    ],
)
def test_invalid_hook_input_is_ignored(tmp_path: Path, case: str) -> None:
    initialize_project(tmp_path)
    if case == "missing-path":
        payload: dict[str, object] | str = {"hook_event_name": "Stop"}
    elif case == "empty-path":
        payload = {"hook_event_name": "Stop", "transcript_path": ""}
    elif case == "missing-file":
        payload = {
            "hook_event_name": "Stop",
            "transcript_path": str(tmp_path / "missing.jsonl"),
        }
    elif case == "not-file":
        payload = {"hook_event_name": "Stop", "transcript_path": str(tmp_path)}
    elif case == "unknown-event":
        payload = {"hook_event_name": "Other"}
    else:
        payload = "not JSON"

    result = run_hook(payload, tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (tmp_path / ".git" / LEDGER).exists()


def test_settings_registers_usage_hook_for_both_events() -> None:
    settings = json.loads((REPOSITORY / ".claude/settings.json").read_text())
    command = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/record-usage.sh'

    for event in ("Stop", "SubagentStop"):
        entries = settings["hooks"][event]
        assert any(
            hook.get("command") == command
            for entry in entries
            for hook in entry.get("hooks", [])
        )
