import json
import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY / ".claude/hooks"
PR_CREATE = " ".join(["gh", "pr", "create"])
CHECKOUT_HARNESS = """\
set -euo pipefail
input="$(cat)"
cmd="$2"
source "$1"
printf '%s\\n' "$dir" "$base"
"""


def hook_environment(project: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(project)
    for name in ("FEWIA_WRITER", "FEWIA_HOOK_HOST"):
        environment.pop(name, None)
    return environment


def run_hook(
    hook: str, payload: dict[str, object], project: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=json.dumps(payload),
        env=hook_environment(project),
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "case", ["cwd", "project", "absolute-cd", "relative-cd", "invalid", "empty"]
)
@pytest.mark.parametrize("base", [None, "claude/x"])
def test_pr_checkout_selection(tmp_path: Path, case: str, base: str | None) -> None:
    project = tmp_path / "project"
    input_cwd = tmp_path / "A"
    absolute_target = tmp_path / "B"
    payload = json.dumps({"cwd": str(input_cwd)})
    command = PR_CREATE
    expected_dir = input_cwd
    if case == "project":
        payload = "{}"
        expected_dir = project
    elif case == "absolute-cd":
        command = f"cd {absolute_target} && {command}"
        expected_dir = absolute_target
    elif case == "relative-cd":
        command = f"cd sub && {command}"
        expected_dir = input_cwd / "sub"
    elif case == "invalid":
        payload = "not json"
        expected_dir = project
    elif case == "empty":
        payload = ""
        expected_dir = project
    if base is not None:
        command += f" --base {base}"

    result = subprocess.run(
        [
            "bash",
            "-c",
            CHECKOUT_HARNESS,
            "checkout-harness",
            str(HOOKS / "pr-checkout.sh"),
            command,
        ],
        input=payload,
        env=hook_environment(project),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        str(expected_dir),
        f"origin/{base or 'main'}",
    ]


def initialize_repository(project: Path) -> str:
    environment = hook_environment(project)
    for arguments in (
        ["init", "--initial-branch=main", str(project)],
        [
            "-C",
            str(project),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "Initialize test repository",
        ],
    ):
        subprocess.run(
            ["git", *arguments],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    result = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("case", ["worktree-cwd", "main-cwd", "absolute-cd"])
def test_pr_done_checkout(tmp_path: Path, case: str) -> None:
    main = tmp_path / "main"
    worktree = tmp_path / "worktree"
    initialize_repository(main)
    sha = initialize_repository(worktree)
    gates = worktree / ".fewia-supervisor-gates"
    gates.mkdir()
    (gates / f"{sha}.json").write_text(
        json.dumps({"clean": True, "gates": [{"status": "PASS"}]}),
        encoding="utf-8",
    )
    reviews = worktree / ".fewia-supervisor-reviews"
    reviews.mkdir()
    (reviews / f"{sha}-model.md").write_text(
        "Review complete.\n\nVERDICT: APPROVE\n\n", encoding="utf-8"
    )
    command = PR_CREATE
    payload: dict[str, object] = {"tool_name": "Bash"}
    if case == "absolute-cd":
        command = f"cd {worktree}/ && {command}"
    else:
        payload["cwd"] = str(worktree if case == "worktree-cwd" else main)
    payload["tool_input"] = {"command": command}

    result = run_hook("check-pr-done.sh", payload, main)

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    if case == "main-cwd":
        assert output["permissionDecision"] == "deny"
        assert "No gates record" in output["permissionDecisionReason"]
    else:
        assert "permissionDecision" not in output
        assert f"Definition of done holds for {sha[:7]}" in output["additionalContext"]


def test_pr_done_ignores_other_commands(tmp_path: Path) -> None:
    result = run_hook(
        "check-pr-done.sh",
        {"cwd": str(tmp_path), "tool_input": {"command": "echo ready"}},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
