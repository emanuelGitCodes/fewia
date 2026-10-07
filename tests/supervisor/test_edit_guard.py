import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("file_path", "writer", "expected"),
    [
        ("backend/app/foo.py", None, "deny"),
        (".claude/hooks/x.sh", None, "allow"),
        (".claude/worktrees/agent-x/backend/app/foo.py", None, "deny"),
        (".claude/worktrees/agent-x/.claude/hooks/x.sh", None, "allow"),
        (".claude/worktrees/agent-x/docs/a.py", None, "allow"),
        (".claude/worktrees/agent-x/README.md", None, "allow"),
        (".claude/worktrees/a/.claude/worktrees/b/backend/x.py", None, "deny"),
        (".claude/worktrees/a/.claude/worktrees/b/wiki/x.json", None, "allow"),
        (".claude/worktrees/notes.json", None, "allow"),
        (
            "{project}/.claude/worktrees/agent-x/frontend/src/App.tsx",
            None,
            "deny",
        ),
        (".claude/worktrees/x/../../../backend/y.py", None, "deny"),
        ("{outside}/backend/app/foo.py", None, "allow"),
        ("backend/app/foo.py", "1", "allow"),
        (".claude/worktrees/agent-x/backend/app/foo.py", "1", "allow"),
        ("backend/app/foo.py", "0", "deny"),
        ("backend/app/foo.py", "true", "deny"),
    ],
)
def test_edit_guard_decision(
    tmp_path: Path, file_path: str, writer: str | None, expected: str
) -> None:
    hook = Path(__file__).resolve().parents[2] / ".claude/hooks/guard-senior-edits.sh"
    path = file_path.format(
        project=tmp_path, outside=tmp_path.parent / "outside-edit-guard"
    )
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    environment.pop("FEWIA_WRITER", None)
    if writer is not None:
        environment["FEWIA_WRITER"] = writer

    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps({"tool_input": {"file_path": path}}),
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    if expected == "allow":
        assert result.stdout == ""
    else:
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
