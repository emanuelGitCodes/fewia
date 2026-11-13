import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY / ".claude/hooks"
PUSH_URL = "git@github.com:example/fewia.git"


def hook_environment(project: Path | None, host: str | None = None) -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")
        if name in os.environ
    }
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


@dataclass
class PublicationRepo:
    project: Path
    environment: dict[str, str]

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project), *arguments],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()

    @property
    def approval(self) -> Path:
        return Path(self.git("rev-parse", "--absolute-git-dir")) / (
            "fewia-publication-approval.json"
        )

    @property
    def command(self) -> str:
        return (
            "git push --no-follow-tags --recurse-submodules=no origin "
            f"{self.git('rev-parse', 'HEAD')}:refs/heads/"
            f"{self.git('branch', '--show-current')}"
        )

    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOKS / "publication-approval.py"), *arguments],
            env=self.environment,
            cwd=self.project,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def record(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "record",
            "--checkout",
            str(self.project),
            "--remote",
            "origin",
            "--push-url",
            PUSH_URL,
            "--branch",
            self.git("branch", "--show-current"),
            "--head",
            self.git("rev-parse", "HEAD"),
            "--source",
            "Current chat: explicit push approval",
            "--reason",
            "Publish the approved feature branch",
            *extra,
        )

    def approved(self, *extra: str) -> str:
        result = self.record(*extra)
        assert result.returncode == 0, result.stderr
        assert result.stdout == self.command + "\n"
        assert self.approval.stat().st_mode & 0o777 == 0o600
        return self.command

    def hook(
        self,
        command: str,
        *,
        host: str | None = "codex",
        wrapper: bool = False,
        location: dict[str, object] | None = None,
        overrides: dict[str, str] | None = None,
        include_cwd: bool = True,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = self.environment.copy()
        environment["CLAUDE_PROJECT_DIR"] = str(self.project)
        environment.pop("FEWIA_HOOK_HOST", None)
        if host is not None:
            environment["FEWIA_HOOK_HOST"] = host
        environment.update(overrides or {})
        payload: dict[str, object] = {
            "tool_input": {"command": command},
        }
        if include_cwd:
            payload["cwd"] = str(self.project)
        payload.update(location or {})
        arguments = (
            [str(self.project / ".claude/hooks/codex-hook.sh"), "guard-bash.sh"]
            if wrapper
            else [str(HOOKS / "guard-bash.sh")]
        )
        return subprocess.run(
            ["bash", *arguments],
            input=json.dumps(payload),
            env=environment,
            cwd=cwd or self.project,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def consume(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        environment = self.environment.copy()
        environment.update(
            CLAUDE_PROJECT_DIR=str(self.project), FEWIA_HOOK_HOST="codex"
        )
        return subprocess.run(
            [
                sys.executable,
                str(HOOKS / "publication-approval.py"),
                "consume",
            ],
            input=json.dumps(payload),
            env=environment,
            cwd=self.project,
            capture_output=True,
            text=True,
            timeout=10,
        )


@pytest.fixture
def publication_repo(tmp_path: Path) -> PublicationRepo:
    project = (tmp_path / "repo").resolve()
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    environment = hook_environment(None)
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home))
    repo = PublicationRepo(project, environment)
    repo.git("init", "--initial-branch=codex/security-hardening")
    repo.git(
        "-c",
        "user.name=Hook",
        "-c",
        "user.email=hook@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--allow-empty",
        "-m",
        "Seed",
    )
    repo.git("remote", "add", "origin", PUSH_URL)
    shutil.copytree(HOOKS, project / ".claude/hooks")
    return repo


def test_publication_record_wrapper_and_replay(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    repo.environment["GIT_PAGER"] = "cat"
    assert_permission(repo.hook(repo.command, wrapper=True), "deny")
    command = repo.approved()
    before = repo.approval.read_bytes()
    assert repo.record().returncode == 1
    assert repo.approval.read_bytes() == before
    assert_permission(repo.hook(command, host=None), "ask")
    assert repo.approval.read_bytes() == before
    assert_permission(repo.hook(command, wrapper=True), "allow")
    assert not repo.approval.exists()
    assert_permission(repo.hook(command, wrapper=True), "deny")


def test_publication_json_framing_whitespace(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    command = repo.approved()
    result = subprocess.run(
        ["bash", str(repo.project / ".claude/hooks/codex-hook.sh"), "guard-bash.sh"],
        input=json.dumps({"tool_input": {"command": command}}) + "\n\n",
        env=repo.environment,
        cwd=repo.project,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert_permission(result, "allow")
    assert not repo.approval.exists()


@pytest.mark.parametrize(
    "change",
    [
        lambda command: " " + command,
        lambda command: command + " ",
        lambda command: command + "\n",
        lambda command: command + "\n\n",
        lambda command: command + "\0",
        lambda command: command.replace("git push", "git  push"),
        lambda command: "env " + command,
        lambda command: "true && " + command,
        lambda command: command + "; true",
        lambda command: command + " && git status",
        lambda command: command + " | cat",
        lambda command: command.replace("origin", "$REMOTE"),
        lambda command: command.replace("origin", "$(echo origin)"),
        lambda command: command.replace("origin", "'origin'"),
        lambda command: command.replace("origin", "other"),
        lambda command: command.replace("refs/heads/codex/", "refs/heads/other/"),
        lambda command: command.replace("refs/heads/", "refs/tags/"),
        lambda command: re.sub(r"[0-9a-f]{40}:", "0" * 40 + ":", command),
        lambda command: command.replace("--no-follow-tags", "--follow-tags"),
        lambda command: command.replace("=no", "=on-demand"),
        lambda command: command + " --tags",
        lambda command: command + " --force",
        lambda command: command + " --no-verify",
        lambda command: command + " && git merge codex/other",
        lambda command: command + " && rm -rf .fewia-supervisor-test",
        lambda command: command.replace("refs/heads/codex/security-hardening", "main"),
        lambda command: "SKIP=gitleaks " + command,
    ],
)
def test_publication_command_mismatch_preserves_record(
    publication_repo: PublicationRepo,
    change: Callable[[str], str],
) -> None:
    repo = publication_repo
    command = repo.approved()
    assert_permission(repo.hook(change(command)), "deny")
    assert repo.approval.exists()
    assert_permission(repo.hook(command), "allow")


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --draft",
        "gh pr edit 494 --title changed",
        "gh pr merge 494",
        "git merge codex/other",
        "gh api repos/example/fewia -X POST",
    ],
)
def test_publication_does_not_grant_other_external_writes(
    publication_repo: PublicationRepo,
    command: str,
) -> None:
    repo = publication_repo
    approved = repo.approved()
    assert_permission(repo.hook(command), "deny")
    assert repo.approval.exists()
    assert_permission(repo.hook(approved), "allow")


@pytest.mark.parametrize("wrapper", [False, True])
@pytest.mark.parametrize(
    "prefix",
    [
        "-C {checkout}",
        "-C '/tmp/a b'",
        '-C"/tmp/a b"',
        "-c key=value",
        '-c "key=value with spaces"',
        "-ckey=value",
        "--git-dir '/tmp/a b'",
        "--git-dir='/tmp/a b'",
        "--work-tree '/tmp/a b'",
        '--work-tree="/tmp/a b"',
        "--no-pager -C {checkout} -c key=value",
    ],
)
def test_publication_global_options_preserve_record(
    publication_repo: PublicationRepo, prefix: str, wrapper: bool
) -> None:
    repo = publication_repo
    command = repo.approved()
    prefix = prefix.format(checkout=repo.project)
    alternative = command.replace("git push", f"git {prefix} push")
    assert_permission(repo.hook(alternative, wrapper=wrapper), "deny")
    assert repo.approval.exists()
    assert_permission(repo.hook(command, wrapper=wrapper), "allow")


@pytest.mark.parametrize("host", [None, "codex"])
@pytest.mark.parametrize(
    "flag",
    [
        "-f",
        "-vf",
        "--f",
        "--for",
        "--force",
        "--force-w",
        "--force-with-lease=refs/heads/feature:abc",
        "--tags",
        "--all",
        "--delete",
        "-d",
        "--mirror",
        "main",
        "--no-verify",
    ],
)
def test_guard_global_options_hard_denies(
    tmp_path: Path, host: str | None, flag: str
) -> None:
    result = run_hook(
        HOOKS / "guard-bash.sh",
        {
            "tool_input": {
                "command": f"git -C '/tmp/a b' -c key=value push origin feature {flag}"
            }
        },
        tmp_path,
        host=host,
    )
    assert_permission(result, "deny")


@pytest.mark.parametrize("wrapper", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        lambda cmd: cmd.replace("git push", "git -C /tmp push") + " --for",
        lambda cmd: cmd.replace("git push", "git -c key=value push") + " -f",
        lambda cmd: cmd.replace("git push", "git --git-dir=/tmp push") + " --tags",
        lambda cmd: cmd.replace("git push", "git --work-tree /tmp push") + " --all",
        lambda cmd: cmd.replace("git push", "git -C /tmp push") + " --delete",
        lambda cmd: "true; " + cmd.replace("git push", "git -C /tmp push"),
        lambda cmd: cmd.replace("git push", "git -c key=value push") + " && true",
        lambda cmd: cmd + "\ngit --no-pager merge codex/other",
        lambda cmd: "git --work-tree '/tmp/a b' merge codex/other",
    ],
)
def test_publication_global_push_flags_and_compounds(
    publication_repo: PublicationRepo,
    change: Callable[[str], str],
    wrapper: bool,
) -> None:
    repo = publication_repo
    command = repo.approved()
    assert_permission(repo.hook(change(command), wrapper=wrapper), "deny")
    assert repo.approval.exists()
    assert_permission(repo.hook(command, wrapper=wrapper), "allow")


@pytest.mark.parametrize("host", [None, "codex"])
@pytest.mark.parametrize(
    "command",
    [
        "git -C '/tmp/a b' status",
        "git -c key=value log --oneline",
        "git --git-dir=/tmp/repo --work-tree '/tmp/a b' diff",
        "git --no-pager show HEAD",
    ],
)
def test_guard_global_options_read_only(
    tmp_path: Path, host: str | None, command: str
) -> None:
    result = run_hook(
        HOOKS / "guard-bash.sh",
        {"tool_input": {"command": command}},
        tmp_path,
        host=host,
    )
    assert_permission(result, "allow")


@pytest.mark.parametrize("host", [None, "codex"])
@pytest.mark.parametrize(
    "command",
    [
        "git -C /tmp push origin feature",
        "git --git-dir='/tmp/a b' merge codex/other",
        "true && git -c key=value push origin feature",
    ],
)
def test_guard_global_options_external_writes(
    tmp_path: Path, host: str | None, command: str
) -> None:
    result = run_hook(
        HOOKS / "guard-bash.sh",
        {"tool_input": {"command": command}},
        tmp_path,
        host=host,
    )
    assert_permission(result, "deny" if host else "ask")


@pytest.mark.parametrize(
    "raw",
    [
        '{"tool_input":',
        "{} {}",
        '{"tool_input": []}',
        '{"tool_input": {"command": null}}',
        '{"tool_input": {"command": false}}',
        '{"tool_input": {"command": "git status"}}\0',
        '{"tool_input": {"command": "git status\\u0000"}}',
        " " * 1048577,
    ],
)
def test_guard_rejects_malformed_payload(tmp_path: Path, raw: str) -> None:
    result = subprocess.run(
        ["bash", str(HOOKS / "guard-bash.sh")],
        input=raw,
        env=hook_environment(tmp_path, "codex"),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert_permission(result, "deny")


@pytest.mark.parametrize("field", ["cwd", "workdir", "project", "relative", "subdir"])
def test_publication_checkout_boundary(
    publication_repo: PublicationRepo,
    tmp_path: Path,
    field: str,
) -> None:
    repo = publication_repo
    command = repo.approved()
    other = str(tmp_path.resolve())
    locations: dict[str, dict[str, object]] = {
        "cwd": {"cwd": other},
        "workdir": {"tool_input": {"command": command, "workdir": other}},
        "project": {},
        "relative": {"cwd": "."},
        "subdir": {"cwd": str(repo.project / ".claude")},
    }
    overrides = {"CLAUDE_PROJECT_DIR": other} if field == "project" else None
    assert_permission(
        repo.hook(command, location=locations[field], overrides=overrides),
        "deny",
    )
    assert_permission(repo.hook(command), "allow")


def test_publication_conflicting_cwd_and_workdir(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    command = repo.approved()
    assert_permission(
        repo.hook(
            command,
            location={
                "cwd": "/missing",
                "tool_input": {"command": command, "workdir": str(repo.project)},
            },
        ),
        "deny",
    )
    assert repo.approval.exists()
    assert_permission(
        repo.hook(
            command,
            location={"tool_input": {"command": command, "workdir": str(repo.project)}},
        ),
        "allow",
    )


def test_publication_actual_wrapper_cwd_fallback(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    command = repo.approved()
    assert_permission(
        repo.hook(
            command, wrapper=True, include_cwd=False, cwd=repo.project / ".claude"
        ),
        "deny",
    )
    assert repo.approval.exists()
    assert_permission(repo.hook(command, wrapper=True, include_cwd=False), "allow")
    assert not repo.approval.exists()


@pytest.mark.parametrize("change", ["head", "branch", "detached"])
def test_publication_head_and_branch_binding(
    publication_repo: PublicationRepo,
    change: str,
) -> None:
    repo = publication_repo
    command = repo.approved()
    head = repo.git("rev-parse", "HEAD")
    if change == "head":
        repo.git(
            "-c",
            "user.name=Hook",
            "-c",
            "user.email=hook@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--allow-empty",
            "-m",
            "Next",
        )
    elif change == "branch":
        repo.git("checkout", "-b", "codex/other")
    else:
        repo.git("checkout", "--detach", head)
    assert_permission(repo.hook(command), "deny")
    assert repo.approval.exists()
    if change == "head":
        repo.git("update-ref", "HEAD", head)
    else:
        repo.git("checkout", "codex/security-hardening")
    assert_permission(repo.hook(command), "allow")


@pytest.mark.parametrize(
    "arguments",
    [
        ("config", "remote.origin.url", "git@github.com:example/other.git"),
        ("config", "remote.origin.pushurl", "https://github.com/example/other.git"),
        ("config", "--add", "remote.origin.pushurl", "file:///tmp/other"),
        ("config", "push.followTags", "true"),
        ("config", "alias.publish", "push"),
        (
            "config",
            "url.https://github.com/example/other.git.insteadOf",
            "git@github.com:example/fewia.git",
        ),
        ("remote", "remove", "origin"),
    ],
)
def test_publication_config_binding(
    publication_repo: PublicationRepo,
    arguments: tuple[str, ...],
) -> None:
    repo = publication_repo
    command = repo.approved()
    config = repo.project / ".git/config"
    original = config.read_bytes()
    repo.git(*arguments)
    assert_permission(repo.hook(command), "deny")
    assert repo.approval.exists()
    config.write_bytes(original)
    assert_permission(repo.hook(command), "allow")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/example/fewia.git",
        "ssh://git@github.com/example/fewia.git",
    ],
)
def test_publication_supported_github_urls(
    publication_repo: PublicationRepo,
    url: str,
) -> None:
    repo = publication_repo
    repo.git("config", "remote.origin.pushurl", url)
    assert_permission(repo.hook(repo.approved("--push-url", url)), "allow")


@pytest.mark.parametrize(
    "url",
    [
        "https://user@github.com/example/fewia.git",
        "http://github.com/example/fewia.git",
        "git@github.com.evil:example/fewia.git",
        "ext::echo invalid",
        "https://github.com/example/fewia.git?extra=yes",
    ],
)
def test_publication_rejects_unsafe_url_at_record(
    publication_repo: PublicationRepo,
    url: str,
) -> None:
    repo = publication_repo
    repo.git("config", "remote.origin.pushurl", url)
    result = repo.record()
    assert result.returncode == 1
    assert url not in result.stderr
    assert not repo.approval.exists()


def test_publication_rejects_multiple_push_urls(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    repo.git("config", "--add", "remote.origin.pushurl", "git@github.com:example/a.git")
    repo.git("config", "--add", "remote.origin.pushurl", "git@github.com:example/b.git")
    assert repo.record().returncode == 1
    assert not repo.approval.exists()


@pytest.mark.parametrize("key", ["remote.origin.url", "remote.origin.pushurl"])
def test_publication_rejects_url_changed_before_recording(
    publication_repo: PublicationRepo, key: str
) -> None:
    repo = publication_repo
    repo.git("config", key, "git@github.com:example/other.git")
    assert repo.record().returncode == 1
    assert not repo.approval.exists()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("remote.origin.mirror", "true"),
        ("remote.origin.mirror", "1"),
        ("push.pushOption", "ci.skip"),
        ("push.pushOption", ""),
        ("remote.origin.vcs", "custom"),
        ("remote.origin.receivepack", "custom-receive-pack"),
        ("core.sshCommand", "ssh -o ProxyCommand=custom"),
    ],
)
def test_publication_rejects_transport_config(
    publication_repo: PublicationRepo, key: str, value: str
) -> None:
    repo = publication_repo
    config = repo.project / ".git/config"
    original = config.read_bytes()
    repo.git("config", key, value)
    assert repo.record().returncode == 1
    assert not repo.approval.exists()
    config.write_bytes(original)
    command = repo.approved()
    repo.git("config", key, value)
    assert_permission(repo.hook(command), "deny")
    assert repo.approval.exists()
    config.write_bytes(original)
    assert_permission(repo.hook(command), "allow")


def test_publication_explicit_refspec_and_push_flags(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    repo.git("config", "remote.origin.mirror", "false")
    repo.git("config", "remote.origin.push", "refs/heads/*:refs/heads/*")
    repo.git("config", "push.followTags", "true")
    repo.git("config", "push.recurseSubmodules", "on-demand")
    repo.git("tag", "unapproved-tag")
    command = repo.approved()
    record = json.loads(repo.approval.read_bytes())
    assert record["argv"] == [
        "git",
        "push",
        "--no-follow-tags",
        "--recurse-submodules=no",
        "origin",
        f"{repo.git('rev-parse', 'HEAD')}:refs/heads/codex/security-hardening",
    ]
    assert record["push_url"] == PUSH_URL
    assert_permission(repo.hook(command), "allow")


@pytest.mark.parametrize(
    "extra",
    [
        ("--branch", "main"),
        ("--branch", "codex/unsafe;true"),
        ("--remote", "origin;true"),
        ("--head", "0" * 40),
        ("--head", "HEAD"),
        ("--push-url", "git@github.com:example/other.git"),
        ("--source", " "),
        ("--reason", ""),
    ],
)
def test_publication_record_requires_explicit_fields(
    publication_repo: PublicationRepo,
    extra: tuple[str, ...],
) -> None:
    repo = publication_repo
    assert repo.record(*extra).returncode == 1
    assert not repo.approval.exists()


def test_publication_record_requires_push_url(
    publication_repo: PublicationRepo,
) -> None:
    repo = publication_repo
    result = repo.cli(
        "record",
        "--checkout",
        str(repo.project),
        "--remote",
        "origin",
        "--branch",
        "codex/security-hardening",
        "--head",
        repo.git("rev-parse", "HEAD"),
        "--source",
        "Current chat",
        "--reason",
        "Approved push",
    )
    assert result.returncode == 2
    assert "--push-url" in result.stderr
    assert not repo.approval.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"GIT_DIR": "/missing"},
        {"GIT_WORK_TREE": "/missing"},
        {"GIT_CONFIG_COUNT": "0"},
        {"GIT_CONFIG_GLOBAL": "/dev/null"},
        {"GIT_SSH_COMMAND": "echo"},
        {"GIT_PUSH_OPTION_COUNT": "1"},
    ],
)
def test_publication_environment_overrides(
    publication_repo: PublicationRepo,
    overrides: dict[str, str],
) -> None:
    repo = publication_repo
    command = repo.approved()
    path = repo.approval
    assert_permission(repo.hook(command, overrides=overrides), "deny")
    assert path.exists()
    head = repo.git("rev-parse", "HEAD")
    original = path.read_bytes()
    path.unlink()
    repo.environment.update(overrides)
    result = repo.cli(
        "record",
        "--checkout",
        str(repo.project),
        "--remote",
        "origin",
        "--push-url",
        PUSH_URL,
        "--branch",
        "codex/security-hardening",
        "--head",
        head,
        "--source",
        "Current chat",
        "--reason",
        "Approved push",
    )
    assert result.returncode == 1
    assert not path.exists()
    for key in overrides:
        del repo.environment[key]
    path.write_bytes(original)
    path.chmod(0o600)
    assert_permission(repo.hook(command), "allow")


@pytest.mark.parametrize(
    "damage",
    [
        "expired",
        "future",
        "long_lifetime",
        "boolean",
        "extra",
        "missing",
        "argv",
        "duplicate",
        "invalid",
        "oversize",
        "mode",
        "symlink",
        "hardlink",
        "fifo",
        "directory",
    ],
)
def test_publication_invalid_record_preserves_approval(
    publication_repo: PublicationRepo,
    damage: str,
) -> None:
    repo = publication_repo
    command = repo.approved()
    path = repo.approval
    original = path.read_bytes()
    record = json.loads(original)
    now = int(time.time())
    backup = path.with_name("approval-backup")
    if damage == "expired":
        record.update(issued=now - 3601, expires=now - 1)
    elif damage == "future":
        record.update(issued=now + 100, expires=now + 200)
    elif damage == "long_lifetime":
        record.update(issued=now - 1, expires=now + 7200)
    elif damage == "boolean":
        record["version"] = True
    elif damage == "extra":
        record["unexpected"] = "value"
    elif damage == "missing":
        del record["reason"]
    elif damage == "argv":
        record["argv"] = [1]
    path.write_text(json.dumps(record), encoding="utf-8")
    if damage == "duplicate":
        path.write_bytes(original[:-2] + b', "version": 1}\n')
    elif damage == "invalid":
        path.write_bytes(b"not json")
    elif damage == "oversize":
        path.write_bytes(b" " * 16385)
    elif damage == "mode":
        path.chmod(0o644)
    elif damage == "symlink":
        path.rename(backup)
        path.symlink_to(backup)
    elif damage == "hardlink":
        os.link(path, backup)
    elif damage in {"fifo", "directory"}:
        path.rename(backup)
        if damage == "fifo":
            os.mkfifo(path, 0o600)
        else:
            path.mkdir(mode=0o600)
    assert_permission(repo.hook(command), "deny")
    assert path.exists()
    assert repo.record().returncode == 1
    if damage == "symlink":
        path.unlink()
        backup.rename(path)
    elif damage == "hardlink":
        backup.unlink()
    elif damage in {"fifo", "directory"}:
        if damage == "fifo":
            path.unlink()
        else:
            path.rmdir()
        backup.rename(path)
    path.write_bytes(original)
    path.chmod(0o600)
    assert_permission(repo.hook(command), "allow")


def test_publication_linked_worktree_has_own_record(
    publication_repo: PublicationRepo,
    tmp_path: Path,
) -> None:
    repo = publication_repo
    command = repo.approved()
    worktree = (tmp_path / "worktree").resolve()
    repo.git("worktree", "add", "-b", "codex/worktree", str(worktree))
    shutil.copytree(HOOKS, worktree / ".claude/hooks")
    linked = PublicationRepo(worktree, repo.environment)
    assert_permission(linked.hook(command, wrapper=True), "deny")
    linked_command = linked.approved()
    assert linked.approval != repo.approval
    assert linked.approval.parent != worktree
    assert_permission(linked.hook(linked_command, wrapper=True), "allow")
    assert repo.approval.exists()
    assert_permission(repo.hook(command, wrapper=True), "allow")


def test_publication_concurrent_consumption(publication_repo: PublicationRepo) -> None:
    repo = publication_repo
    command = repo.approved()
    barrier = Barrier(2)

    def invoke() -> subprocess.CompletedProcess[str]:
        barrier.wait(timeout=10)
        return repo.hook(command, wrapper=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sum(result.stdout == "" for result in results) == 1
    for result in results:
        assert_permission(result, "allow" if result.stdout == "" else "deny")
    assert not repo.approval.exists()


@pytest.mark.parametrize(
    "field",
    ["tool", "command", "cwd", "workdir", "noncanonical", "alias", "flags"],
)
def test_publication_checker_rejects_malformed_context(
    publication_repo: PublicationRepo,
    field: str,
) -> None:
    repo = publication_repo
    command = repo.approved()
    tool: dict[str, object] = {"command": command}
    payload: dict[str, object] = {"tool_input": tool}
    if field == "tool":
        payload["tool_input"] = []
    elif field == "command":
        tool["command"] = [command]
    elif field == "cwd":
        payload["cwd"] = None
    elif field == "workdir":
        tool["workdir"] = None
    elif field == "noncanonical":
        payload["cwd"] = str(repo.project) + "/../repo"
    elif field == "alias":
        tool["command"] = command.replace("git push", "git publish")
    else:
        tool["command"] = command.replace("git push", "git --no-pager push")
    assert repo.consume(payload).returncode == 1
    assert repo.approval.exists()
    assert_permission(repo.hook(command), "allow")
