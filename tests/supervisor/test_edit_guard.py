import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest


def assert_edit_guard_decision(
    project: Path,
    file_path: str,
    writer: str | None,
    expected: str,
    *,
    extra_path: Path | None = None,
) -> None:
    hook = Path(__file__).resolve().parents[2] / ".claude/hooks/guard-senior-edits.sh"
    environment = os.environ.copy()
    if extra_path is not None:
        environment["PATH"] = (
            f"{extra_path}{os.pathsep}{environment.get('PATH', os.defpath)}"
        )
    environment["CLAUDE_PROJECT_DIR"] = str(project)
    environment.pop("FEWIA_WRITER", None)
    if writer is not None:
        environment["FEWIA_WRITER"] = writer

    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps({"tool_input": {"file_path": file_path}}),
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
    path = file_path.format(
        project=tmp_path, outside=tmp_path.parent / "outside-edit-guard"
    )
    assert_edit_guard_decision(tmp_path, path, writer, expected)


@pytest.fixture
def checkout_paths(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path.resolve()
    main = root / "main"
    session = main / ".claude/worktrees/session"
    sibling = root / "sibling"
    odd = root / "odd\nname"
    commands = [
        ["git", "init", str(main)],
        [
            "git",
            "-C",
            str(main),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "Create test checkout",
        ],
        ["git", "-C", str(main), "worktree", "add", "-b", "session", str(session)],
        ["git", "-C", str(main), "worktree", "add", "-b", "sibling", str(sibling)],
        ["git", "-C", str(main), "worktree", "add", "-b", "odd", str(odd)],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)

    link = root / "link"
    link.symlink_to(main, target_is_directory=True)
    return {
        "main": main,
        "session": session,
        "sibling": sibling,
        "odd": odd,
        "outside": root / "outside",
        "link": link,
    }


@pytest.mark.parametrize(
    ("file_path", "writer", "expected"),
    [
        ("{main}/backend/app/foo.py", None, "deny"),
        ("{main}/wiki/log.md", None, "allow"),
        ("{main}/.claude/hooks/x.sh", None, "allow"),
        ("{sibling}/backend/app/foo.py", None, "deny"),
        ("{sibling}/docs/x.md", None, "allow"),
        ("{odd}/backend/app/foo.py", None, "deny"),
        ("{odd}/docs/x.md", None, "allow"),
        ("../../../backend/app/foo.py", None, "deny"),
        ("backend/app/foo.py", None, "deny"),
        ("{outside}/backend/app/foo.py", None, "allow"),
        ("{link}/backend/x.py", None, "deny"),
        ("{main}/backend/app/foo.py", "1", "allow"),
    ],
)
def test_edit_guard_checkout_decision(
    checkout_paths: dict[str, Path],
    file_path: str,
    writer: str | None,
    expected: str,
) -> None:
    assert_edit_guard_decision(
        checkout_paths["session"], file_path.format(**checkout_paths), writer, expected
    )


def test_edit_guard_ignores_failed_git_listing(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    project = root / "project"
    project.mkdir()
    sibling = root / "sibling"
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    fake_git = bin_path / "git"
    fake_git.write_text(
        f"#!/bin/bash\nprintf 'worktree %s\\0' {shlex.quote(str(sibling))}\nexit 1\n"
    )
    fake_git.chmod(0o755)

    assert_edit_guard_decision(
        project, str(sibling / "backend/app/foo.py"), None, "allow", extra_path=bin_path
    )
    assert_edit_guard_decision(
        project, str(project / "backend/app/foo.py"), None, "deny", extra_path=bin_path
    )
