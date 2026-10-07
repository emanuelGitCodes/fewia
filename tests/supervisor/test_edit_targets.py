import json
import os
import subprocess
from pathlib import Path

import pytest

LOG_CONTENTS = "# Log\n\nentry one\nentry two\n"


def assert_edit_targets(
    project: Path,
    payload: dict[str, object],
    expected: list[dict[str, object]],
) -> None:
    hook = Path(__file__).resolve().parents[2] / ".claude/hooks/edit-targets.py"
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        ["python3", str(hook)],
        input=json.dumps(payload),
        env=environment,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize(
    ("log_contents", "hunk", "appends"),
    [
        (LOG_CONTENTS, " entry two\n+three\n", True),
        (LOG_CONTENTS, " # Log\n+inserted\n", False),
        (LOG_CONTENTS, "+inserted\n entry one\n", False),
        (LOG_CONTENTS, "+x\n", False),
        (
            LOG_CONTENTS,
            " entry one\n entry two\n+three\n*** End of File\n",
            True,
        ),
        (LOG_CONTENTS, "-entry two\n+x\n", False),
        ("# Log\n\nentry\n\nentry\n", " entry\n+x\n", False),
        (None, " entry two\n+x\n", False),
        ("", "+x\n", True),
    ],
    ids=[
        "append-at-end",
        "insert-after-header",
        "context-after-addition",
        "no-context",
        "end-of-file-marker",
        "removal",
        "repeated-context",
        "missing-file",
        "empty-file",
    ],
)
def test_edit_targets_update_appends(
    tmp_path: Path, log_contents: str | None, hunk: str, appends: bool
) -> None:
    log = tmp_path / "wiki/log.md"
    if log_contents is not None:
        log.parent.mkdir()
        log.write_text(log_contents)
    patch = f"*** Begin Patch\n*** Update File: wiki/log.md\n@@\n{hunk}*** End Patch\n"

    assert_edit_targets(
        tmp_path,
        {
            "tool_name": "apply_patch",
            "cwd": str(tmp_path),
            "tool_input": {"command": patch},
        },
        [{"path": str(log), "op": "update", "appends": appends}],
    )


def test_edit_targets_move(tmp_path: Path) -> None:
    patch = (
        "*** Begin Patch\n*** Update File: docs/a.md\n"
        "*** Move to: backend/a.py\n@@\n-old\n+new\n*** End Patch\n"
    )

    assert_edit_targets(
        tmp_path,
        {
            "tool_name": "apply_patch",
            "cwd": str(tmp_path),
            "tool_input": {"command": patch},
        },
        [
            {
                "path": str(tmp_path / "docs/a.md"),
                "op": "move_from",
                "appends": False,
            },
            {
                "path": str(tmp_path / "backend/a.py"),
                "op": "move_to",
                "appends": False,
            },
        ],
    )


def test_edit_targets_claude_edit(tmp_path: Path) -> None:
    assert_edit_targets(
        tmp_path,
        {"tool_name": "Edit", "tool_input": {"file_path": "docs/a.md"}},
        [{"path": str(tmp_path / "docs/a.md"), "op": "Edit", "appends": False}],
    )
