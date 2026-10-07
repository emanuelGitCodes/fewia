import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY / ".claude/hooks"


def hook_environment(project: Path | None, host: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("CLAUDE_PROJECT_DIR", "FEWIA_WRITER", "FEWIA_HOOK_HOST"):
        environment.pop(name, None)
    if project is not None:
        environment["CLAUDE_PROJECT_DIR"] = str(project)
    if host is not None:
        environment["FEWIA_HOOK_HOST"] = host
    return environment


def patch_input(project: Path, body: str) -> dict[str, object]:
    return {
        "tool_name": "apply_patch",
        "cwd": str(project),
        "tool_input": {"command": f"*** Begin Patch\n{body}*** End Patch\n"},
    }


def run_hook(
    hook: Path,
    payload: dict[str, object],
    project: Path | None,
    *,
    host: str | None = None,
    cwd: Path | None = None,
    arguments: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook), *arguments],
        input=json.dumps(payload),
        env=hook_environment(project, host),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )


def assert_permission(result: subprocess.CompletedProcess[str], expected: str) -> None:
    assert result.returncode == 0, result.stderr
    if expected == "allow":
        assert result.stdout == ""
    else:
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert output["hookEventName"] == "PreToolUse"
        assert output["permissionDecision"] == expected


@pytest.mark.parametrize(
    ("body", "log_content", "expected"),
    [
        (
            "*** Update File: wiki/log.md\n@@\n entry\n+new entry\n",
            "# Log\nentry\n",
            "allow",
        ),
        (
            "*** Update File: wiki/log.md\n@@\n # Log\n+inserted\n",
            "# Log\nentry\n",
            "deny",
        ),
        (
            "*** Update File: wiki/log.md\n@@\n+inserted\n entry\n",
            "# Log\nentry\n",
            "deny",
        ),
        (
            "*** Update File: wiki/log.md\n@@\n+x\n",
            "# Log\nentry\n",
            "deny",
        ),
        (
            "*** Update File: wiki/log.md\n@@\n entry\n+x\n",
            "# Log\nentry\n\nentry\n",
            "deny",
        ),
        (
            "*** Update File: wiki/log.md\n@@\n-entry\n+changed\n",
            "# Log\nentry\n",
            "deny",
        ),
        ("*** Delete File: wiki/log.md\n", "# Log\nentry\n", "deny"),
        (
            "*** Add File: wiki/log.md\n+# Log\n+new entry\n",
            "# Log\nentry\n",
            "deny",
        ),
        ("*** Add File: wiki/log.md\n+# Log\n+new entry\n", None, "allow"),
        (
            "*** Update File: wiki/log.md\n*** Move to: wiki/old-log.md\n@@\n entry\n",
            "# Log\nentry\n",
            "deny",
        ),
        (
            "*** Update File: wiki/index.md\n@@\n-entry\n+changed\n",
            "# Log\nentry\n",
            "allow",
        ),
    ],
    ids=[
        "append",
        "insert-after-first-line",
        "insert-before-context",
        "no-context",
        "repeated-context",
        "replace",
        "delete",
        "overwrite",
        "create",
        "move",
        "index",
    ],
)
def test_wiki_log_apply_patch(
    tmp_path: Path, body: str, log_content: str | None, expected: str
) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    if log_content is not None:
        (wiki / "log.md").write_text(log_content, encoding="utf-8")
    (wiki / "index.md").write_text("entry\n", encoding="utf-8")

    result = run_hook(
        HOOKS / "guard-wiki-log.sh", patch_input(tmp_path, body), tmp_path
    )

    assert_permission(result, expected)


def test_wiki_log_claude_edit(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "log.md").write_text("# Log\nentry\n", encoding="utf-8")
    result = run_hook(
        HOOKS / "guard-wiki-log.sh",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "wiki/log.md",
                "old_string": "entry",
                "new_string": "changed",
            },
        },
        tmp_path,
    )

    assert_permission(result, "deny")


@pytest.mark.parametrize("content", ["Please utilize this file.\n", "Use this file.\n"])
def test_lint_prose_apply_patch(tmp_path: Path, content: str) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text(content, encoding="utf-8")
    result = run_hook(
        HOOKS / "lint-prose.sh",
        patch_input(tmp_path, "*** Add File: docs/a.md\n+Use this file.\n"),
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    if "utilize" in content:
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert output["hookEventName"] == "PostToolUse"
        assert "docs/a.md" in output["additionalContext"]
        assert "utilize" in output["additionalContext"]
    else:
        assert result.stdout == ""


@pytest.mark.parametrize("host", [None, "codex"])
@pytest.mark.parametrize("command", ["git push origin feature", "git status"])
def test_guard_bash(tmp_path: Path, host: str | None, command: str) -> None:
    result = run_hook(
        HOOKS / "guard-bash.sh",
        {"tool_name": "Bash", "tool_input": {"command": command}},
        tmp_path,
        host=host,
    )

    expected = "allow" if command == "git status" else "deny" if host else "ask"
    assert_permission(result, expected)
    if expected == "deny":
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert "cannot ask" in output["permissionDecisionReason"]


def test_codex_wrapper_finds_repository_from_subdirectory(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    subprocess.run(
        ["git", "init", str(project)],
        env=hook_environment(None),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    shutil.copytree(HOOKS, project / ".claude/hooks")
    subdirectory = project / "backend"
    subdirectory.mkdir()
    result = run_hook(
        project / ".claude/hooks/codex-hook.sh",
        patch_input(project, "*** Add File: backend/x.py\n+pass\n"),
        None,
        cwd=subdirectory,
        arguments=("guard-senior-edits.sh",),
    )

    assert_permission(result, "deny")
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert "backend/x.py" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "argument", ["../guard-senior-edits.sh", "hooks/guard-bash.sh"]
)
def test_codex_wrapper_rejects_script_paths(tmp_path: Path, argument: str) -> None:
    result = run_hook(
        HOOKS / "codex-hook.sh", {}, None, cwd=tmp_path, arguments=(argument,)
    )

    assert result.returncode == 1
    assert "give one hook file name" in result.stderr


def test_codex_hook_configuration() -> None:
    configuration = json.loads(
        (REPOSITORY / ".codex/hooks.json").read_text(encoding="utf-8")
    )
    edit_hooks: set[tuple[str, str]] = set()
    command_count = 0
    for event, groups in configuration["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                assert hook["type"] == "command"
                parts = shlex.split(hook["command"])
                assert len(parts) == 2
                assert parts[0] == (
                    "$(git rev-parse --show-toplevel)/.claude/hooks/codex-hook.sh"
                )
                script = parts[1]
                assert Path(script).name == script
                assert (HOOKS / script).is_file()
                command_count += 1
                if re.fullmatch(group.get("matcher", ""), "apply_patch"):
                    edit_hooks.add((event, script))

    assert command_count > 0
    assert {
        ("PreToolUse", "guard-senior-edits.sh"),
        ("PreToolUse", "guard-wiki-log.sh"),
        ("PostToolUse", "lint-prose.sh"),
    } <= edit_hooks
