import json
import subprocess
import sys
from pathlib import Path
from typing import IO

import pytest

from dev_supervisor import review
from dev_supervisor.usage import ledger_path


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.check_call(["git", "init"], cwd=root, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "dev@example.test"], cwd=root)
    subprocess.check_call(["git", "config", "user.name", "Dev"], cwd=root)
    subprocess.check_call(["git", "config", "commit.gpgsign", "false"], cwd=root)
    (root / "keep.txt").write_text("ok\n")
    subprocess.check_call(["git", "add", "keep.txt"], cwd=root)
    subprocess.check_call(
        ["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.DEVNULL
    )
    agents = root / ".codex" / "agents"
    agents.mkdir(parents=True)
    (agents / "code-reviewer.toml").write_text(
        'developer_instructions = """REVIEWER ROLE"""\n'
    )
    (root / "brief.txt").write_text("BRIEF BODY\n")
    return root


def sha_of(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def argv(
    root: Path,
    extra: list[str] | None = None,
    complexity: str = "standard",
    writer: str = "grok-4.6",
    brief: Path | None = None,
) -> list[str]:
    return [
        "review",
        "--cwd",
        str(root),
        "--base",
        "HEAD",
        "--brief",
        str(brief or root / "brief.txt"),
        "--complexity",
        complexity,
        "--writer-model",
        writer,
        *(extra or []),
    ]


def run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exit_info:
        review.main()
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def install_run(
    monkeypatch: pytest.MonkeyPatch,
    message: str = "notes\nVERDICT: APPROVE\n",
    stdout: bytes = b"",
    timed_out: bool = False,
    elapsed_ms: int = 4,
    write: bool = True,
) -> dict[str, object]:
    seen: dict[str, object] = {}

    def fake(
        args: list[str], cwd: Path, stdin: IO[bytes], timeout: float
    ) -> tuple[bytes, bool, int]:
        seen["args"] = args
        seen["cwd"] = cwd
        seen["timeout"] = timeout
        seen["prompt_path"] = Path(stdin.name)
        seen["prompt"] = stdin.read().decode()
        dest = Path(args[args.index("-o") + 1])
        seen["dest"] = dest
        if write:
            dest.write_text(message)
        return stdout, timed_out, elapsed_ms

    monkeypatch.setattr(review, "run_codex", fake)
    return seen


def summary(stdout: str) -> dict[str, object]:
    return json.loads(stdout.splitlines()[-1])


def refuse_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("codex MUST NOT start")

    monkeypatch.setattr(review, "run_codex", boom)


@pytest.mark.parametrize(
    ("writer", "expected"),
    [
        ("grok-4.6", "gpt-6-luna"),
        ("gpt-5.3-codex-spark", "gpt-6-luna"),
        ("gpt-6-luna", "gpt-6-sol"),
        ("gpt-6-sol", "gpt-6-luna"),
        ("unknown-writer", "gpt-6-luna"),
    ],
)
def test_review_model_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    writer: str,
    expected: str,
) -> None:
    root = make_repo(tmp_path)
    install_run(monkeypatch)
    code = run_main(monkeypatch, argv(root, writer=writer))
    assert code == 0
    data = summary(capsys.readouterr().out)
    assert data["model"] == expected
    assert data["verdict"] == "APPROVE"
    dest = Path(str(data["saved"]))
    assert dest.name == f"{sha_of(root)}-{expected}.md"


def test_explicit_model_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    install_run(monkeypatch)
    code = run_main(monkeypatch, argv(root, ["--model", "gpt-6-sol"]))
    assert code == 0
    assert summary(capsys.readouterr().out)["model"] == "gpt-6-sol"


def test_refuses_matching_review_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    refuse_codex(monkeypatch)
    code = run_main(monkeypatch, argv(root, ["--model", "grok-4.6"]))
    assert code == 2
    assert "Review model MUST NOT equal writer model" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("complexity", "effort"),
    [
        ("simple", "low"),
        ("standard", "medium"),
        ("complex", "high"),
        ("exceptional", "high"),
        ("maximum", "high"),
    ],
)
def test_effort_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    complexity: str,
    effort: str,
) -> None:
    root = make_repo(tmp_path)
    seen = install_run(monkeypatch)
    code = run_main(monkeypatch, argv(root, complexity=complexity))
    assert code == 0
    data = summary(capsys.readouterr().out)
    assert data["effort"] == effort
    args = seen["args"]
    assert isinstance(args, list)
    assert f'model_reasoning_effort="{effort}"' in args


def test_dirty_tree_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    (root / "keep.txt").write_text("changed\n")
    refuse_codex(monkeypatch)
    code = run_main(monkeypatch, argv(root))
    assert code == 2
    assert "Tracked tree is dirty" in capsys.readouterr().err


def test_missing_brief_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    refuse_codex(monkeypatch)
    code = run_main(monkeypatch, argv(root, brief=root / "missing.txt"))
    assert code == 2
    assert "Brief file not found" in capsys.readouterr().err


def test_prompt_includes_role_guard_range_brief_and_gates_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    gates = tmp_path / "gates.json"
    gates.write_text('{"ok": true}\n')
    seen = install_run(monkeypatch)
    code = run_main(monkeypatch, argv(root, ["--gates-file", str(gates)]))
    assert code == 0
    prompt = seen["prompt"]
    assert isinstance(prompt, str)
    assert "REVIEWER ROLE" in prompt
    assert "Do not modify files. Do not run tests, package managers, or commands" in (
        prompt
    )
    assert "that write. The coordinator ran the gates; their record follows when" in (
        prompt
    )
    assert f"Review range: HEAD...{sha_of(root)}" in prompt
    assert "BRIEF BODY" in prompt
    assert "Gates:\n" in prompt
    assert '{"ok": true}' in prompt
    assert "End the review with exactly one line" in prompt
    args = seen["args"]
    assert isinstance(args, list)
    assert args[0:4] == ["codex", "exec", "--model", "gpt-6-luna"]
    assert "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
    assert args[-1] == "-"


def test_prompt_reads_default_gates_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    sha = sha_of(root)
    path = root / ".fewia-supervisor-gates" / f"{sha}.json"
    path.parent.mkdir()
    path.write_text('{"from": "default"}\n')
    seen = install_run(monkeypatch)
    code = run_main(monkeypatch, argv(root))
    assert code == 0
    prompt = seen["prompt"]
    assert isinstance(prompt, str)
    assert "Gates:\n" in prompt
    assert '{"from": "default"}' in prompt


def test_last_verdict_line_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    install_run(monkeypatch, message="VERDICT: APPROVE\nVERDICT: REQUEST_CHANGES\n")
    assert run_main(monkeypatch, argv(root)) == 1
    assert summary(capsys.readouterr().out)["verdict"] == "REQUEST_CHANGES"


@pytest.mark.parametrize(
    ("message", "verdict", "code"),
    [
        ("ok\nVERDICT: APPROVE\n", "APPROVE", 0),
        ("fix\nVERDICT: REQUEST_CHANGES\n", "REQUEST_CHANGES", 1),
        ("stop\nVERDICT: BLOCKED\n", "BLOCKED", 2),
        ("no verdict line\n", "BLOCKED", 2),
    ],
)
def test_verdict_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    message: str,
    verdict: str,
    code: int,
) -> None:
    root = make_repo(tmp_path)
    install_run(monkeypatch, message=message)
    assert run_main(monkeypatch, argv(root)) == code
    assert summary(capsys.readouterr().out)["verdict"] == verdict


def test_stale_review_file_is_not_a_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    dest = root / ".fewia-supervisor-reviews" / f"{sha_of(root)}-gpt-6-luna.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("VERDICT: APPROVE\n")
    install_run(monkeypatch, write=False)
    code = run_main(monkeypatch, argv(root))
    assert code == 2
    assert summary(capsys.readouterr().out)["verdict"] != "APPROVE"


def test_run_codex_starts_new_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class FakeProc:
        def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
            return b"", None

    def popen(*args: object, **kwargs: object) -> FakeProc:
        captured.update(kwargs)
        return FakeProc()

    monkeypatch.setattr(review.subprocess, "Popen", popen)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("ok\n")
    with prompt.open("rb") as source:
        review.run_codex(["codex"], tmp_path, source, 1.0)
    assert captured["start_new_session"] is True


def test_missing_report_is_not_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    seen = install_run(monkeypatch, write=False)
    assert run_main(monkeypatch, argv(root)) == 2
    row = json.loads(ledger_path(root).read_text().splitlines()[0])
    assert row["outcome"] == "task_failed"
    dest = seen["dest"]
    assert isinstance(dest, Path)
    banned = ("VERDICT: APPROVE", "VERDICT: REQUEST_CHANGES", "VERDICT: BLOCKED")
    for line in dest.read_text().splitlines():
        assert line not in banned
    prompt_path = seen["prompt_path"]
    assert isinstance(prompt_path, Path)
    assert not prompt_path.exists()


class TimeoutProc:
    def __init__(self) -> None:
        self.pid = 99

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        if timeout is not None:
            raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout)
        return b"", None


def test_timeout_calls_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    stopped: list[object] = []
    real = subprocess.Popen

    def popen(cmd: list[str], *args: object, **kwargs: object) -> object:
        if cmd and cmd[0] == "codex":
            return TimeoutProc()
        return real(cmd, *args, **kwargs)

    def fake_stop(proc: object) -> bool:
        stopped.append(proc)
        return True

    monkeypatch.setattr(review.subprocess, "Popen", popen)
    monkeypatch.setattr(review, "stop", fake_stop)
    captured: dict[str, Path] = {}
    real_run = review.run_codex

    def capturing_run(
        args: list[str], cwd: Path, stdin: IO[bytes], timeout: float
    ) -> tuple[bytes, bool, int]:
        captured["prompt_path"] = Path(stdin.name)
        return real_run(args, cwd, stdin, timeout)

    monkeypatch.setattr(review, "run_codex", capturing_run)
    code = run_main(monkeypatch, argv(root, ["--timeout", "0.01"]))
    assert code == 2
    assert stopped
    data = summary(capsys.readouterr().out)
    assert data["verdict"] == "BLOCKED"
    row = json.loads(ledger_path(root).read_text().splitlines()[0])
    assert row["outcome"] == "timeout"
    assert not captured["prompt_path"].exists()


def test_stdout_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(tmp_path)
    long_msg = "\n".join(f"line{i}" for i in range(61)) + "\n"
    seen = install_run(monkeypatch, message=long_msg)
    run_main(monkeypatch, argv(root))
    out = capsys.readouterr().out
    dest = str(seen["dest"])
    assert f"... truncated, full text: {dest}" in out
    assert "line59" in out
    assert "line60" not in "\n".join(out.splitlines()[:60])
    short_msg = "\n".join(f"line{i}" for i in range(60)) + "\n"
    install_run(monkeypatch, message=short_msg)
    run_main(monkeypatch, argv(root))
    short_out = capsys.readouterr().out
    assert "... truncated, full text:" not in short_out


def test_usage_row_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_repo(tmp_path)
    event = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 1,
                "output_tokens": 5,
                "reasoning_output_tokens": 2,
            },
        }
    )
    seen = install_run(monkeypatch, stdout=(event + "\n").encode())
    code = run_main(monkeypatch, argv(root, ["--work-item", "cap-1"]))
    assert code == 0
    prompt_path = seen["prompt_path"]
    assert isinstance(prompt_path, Path)
    assert not prompt_path.exists()
    row = json.loads(ledger_path(root).read_text().splitlines()[0])
    assert row["phase"] == "review"
    assert row["provider"] == "codex"
    assert row["work_item"] == "cap-1"
    assert row["model"] == "gpt-6-luna"
    assert row["effort"] == "medium"
    assert row["outcome"] == "completed"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5
    assert row["provenance"] == "codex.turn.completed"
