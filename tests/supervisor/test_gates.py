import json
import signal
import subprocess
from pathlib import Path

import pytest

from dev_supervisor.gates import (
    GATE_KILL_GRACE,
    GateRow,
    _run_gate,
    areas_for,
    changed_paths,
    count_added_lines,
    format_output,
    is_clean,
    load_reuse,
    main,
    run_area_gates,
    write_record,
)

_REAL_RUN = subprocess.run


def _git(cwd: Path, *args: str) -> str:
    done = _REAL_RUN(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return done.stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "keep.txt").write_text("a\n")
    (repo / ".gitignore").write_text(".fewia-supervisor*/\nignored/\n")
    _git(repo, "add", "keep.txt", ".gitignore")
    _git(repo, "commit", "-m", "init")
    return repo


def _commit_backend(repo: Path) -> str:
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    _git(repo, "add", "backend/x.py")
    _git(repo, "commit", "-m", "Add backend source")
    return base


def _route(code: int = 0, output: str = "ok\n") -> object:
    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        return subprocess.CompletedProcess(argv, code, output, "")

    return inner


def test_area_backend() -> None:
    assert areas_for({"backend/app/main.py"}) == {"backend"}


def test_area_frontend() -> None:
    assert areas_for({"frontend/src/App.tsx"}) == {"frontend"}


def test_area_dev_supervisor() -> None:
    assert areas_for({"dev_supervisor/gates.py"}) == {"tools"}


def test_area_tests() -> None:
    assert areas_for({"tests/supervisor/test_gates.py"}) == {"tools"}


def test_area_infra_python() -> None:
    assert areas_for({"infra/floci_bootstrap.py"}) == {"tools"}


def test_area_ruff_toml() -> None:
    assert areas_for({"ruff.toml"}) == {"tools"}


def test_area_cdk_priority() -> None:
    assert areas_for({"infra/bedrock/stack.py"}) == {"cdk"}


@pytest.mark.parametrize(
    "path",
    [
        "infra/hosting/app.py",
        "infra/hosting/tests/test_resources.py",
        "infra/hosting/README.md",
        "infra/hosting/pyproject.toml",
        "infra/hosting/cdk.json",
        "infra/hosting/uv.lock",
        "infra/hosting/nested/other.txt",
    ],
)
def test_area_hosting_priority(path: str) -> None:
    assert areas_for({path}) == {"hosting"}


def test_area_hosting_mixed_paths() -> None:
    paths = {
        "infra/hosting/uv.lock",
        "infra/bedrock/README.md",
        "infra/floci_bootstrap.py",
        "backend/app/main.py",
        "frontend/src/App.tsx",
        "tests/supervisor/test_gates.py",
        "compose.yaml",
        "docs/plan.md",
    }
    assert areas_for(paths) == {
        "hosting",
        "cdk",
        "tools",
        "backend",
        "frontend",
        "compose",
    }


def test_area_docs_only() -> None:
    paths = {
        "docs/plan.md",
        "wiki/log.md",
        "README.md",
        ".github/a.yml",
    }
    assert areas_for(paths) == set()


def test_area_compose_root_yaml() -> None:
    assert areas_for({"compose.yaml"}) == {"compose"}
    assert areas_for({"compose.override.yaml"}) == {"compose"}
    assert areas_for({"nested/compose.yaml"}) == set()


def test_changed_paths_union(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "keep.txt").write_text("a\nb\n")
    (repo / "new.py").write_text("x\n")
    paths = changed_paths(repo, "HEAD")
    assert "keep.txt" in paths
    assert "new.py" in paths


def test_count_excludes_tests_docs_lock_and_includes_untracked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "keep.txt").write_text("a\nb\n")
    (repo / "app.py").write_text("one\ntwo\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "hidden.py").write_text("x\n" * 8)
    (repo / "note.md").write_text("docs\n")
    (repo / "uv.lock").write_text("lock\n")
    (repo / "package-lock.json").write_text("{}\n")
    (repo / "foo.test.ts").write_text("spec\n")
    assert count_added_lines(repo, "HEAD") == 3


def test_format_pass_skip() -> None:
    text = format_output(
        [
            ("backend", "ruff-check", "PASS", "All checks passed!", ()),
            ("backend", "mypy", "PASS", "", ()),
        ],
        12,
        {"backend"},
    )
    assert text.splitlines() == [
        "PASS backend:ruff-check All checks passed!",
        "PASS backend:mypy ",
        "LINES 12/150",
        "RESULT PASS",
    ]


def test_format_fail_tail() -> None:
    tail = tuple(f"L{i}" for i in range(5, 25))
    text = format_output(
        [("backend", "pytest", "FAIL", "L24", tail)],
        1,
        {"backend"},
    )
    lines = text.splitlines()
    assert lines[0] == "FAIL backend:pytest L24"
    assert lines[1:21] == [f"  L{i}" for i in range(5, 25)]
    assert lines[21] == "LINES 1/150"
    assert lines[22] == "RESULT FAIL"


def test_format_no_gates() -> None:
    assert format_output([], 0, set()) == "RESULT PASS (no gates for these paths)\n"


def test_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProc:
        pid = 4242

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(cmd=["uv"], timeout=timeout or 0)

    def fake_popen(*args: object, **kwargs: object) -> FakeProc:
        assert kwargs.get("start_new_session") is True
        return FakeProc()

    killed: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killed.append((pgid, sig))

    monkeypatch.setattr("dev_supervisor.gates.subprocess.Popen", fake_popen)
    monkeypatch.setattr("dev_supervisor.gates.os.killpg", fake_killpg)
    try:
        _run_gate(("uv",), cwd=tmp_path, timeout=1.0, env=None)
    except subprocess.TimeoutExpired:
        status = "FAIL"
        last_line = "timeout"
        tail: tuple[str, ...] = ()
    else:
        raise AssertionError("expected TimeoutExpired")
    assert status == "FAIL"
    assert last_line == "timeout"
    assert tail == ()
    assert killed == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


def test_timeout_killpg_process_lookup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProc:
        pid = 4242

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if timeout == GATE_KILL_GRACE:
                return ("", "")
            raise subprocess.TimeoutExpired(cmd=["uv"], timeout=timeout or 0)

    def fake_popen(*args: object, **kwargs: object) -> FakeProc:
        assert kwargs.get("start_new_session") is True
        return FakeProc()

    killed: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killed.append((pgid, sig))
        raise ProcessLookupError

    monkeypatch.setattr("dev_supervisor.gates.subprocess.Popen", fake_popen)
    monkeypatch.setattr("dev_supervisor.gates.os.killpg", fake_killpg)
    try:
        _run_gate(("uv",), cwd=tmp_path, timeout=1.0, env=None)
    except subprocess.TimeoutExpired:
        status = "FAIL"
        last_line = "timeout"
        tail: tuple[str, ...] = ()
    else:
        raise AssertionError("expected TimeoutExpired")
    assert status == "FAIL"
    assert last_line == "timeout"
    assert tail == ()
    assert killed == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


def test_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_text("x\n")
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 0
    assert capsys.readouterr().out == "RESULT PASS (no gates for these paths)\n"
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 0
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route(1, "bad\n"))
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 1


def test_frontend_runs_lint_test_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    results = run_area_gates(tmp_path, {"frontend"}, 5)
    assert [gate for _, gate, _, _, _ in results] == [
        "npm-ci",
        "lint",
        "test",
        "build",
    ]
    assert [status for _, _, status, _, _ in results] == [
        "PASS",
        "PASS",
        "PASS",
        "PASS",
    ]


def test_tools_sets_pythonpath(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(kwargs.get("env"))
        return subprocess.CompletedProcess(["uv"], 0, "ok\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", inner)
    run_area_gates(tmp_path, {"tools"}, 5)
    assert seen
    for env in seen:
        assert isinstance(env, dict)
        assert env["PYTHONPATH"] == "."


def test_hosting_dispatches_project_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_run(
        argv: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == tmp_path / "infra" / "hosting"
        assert timeout == 17
        assert env is None
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", fake_run)
    results = run_area_gates(tmp_path, {"hosting"}, 17)
    assert seen == [
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "mypy", "--strict", "."),
        ("uv", "run", "pytest", "-q"),
    ]
    assert results == [
        ("hosting", gate, "PASS", "ok", ("ok",))
        for gate in ("ruff-check", "ruff-format", "mypy", "pytest")
    ]


@pytest.mark.parametrize("failure", ["exit", "timeout"])
@pytest.mark.parametrize("failed_index", range(4))
def test_hosting_failure_reaches_exit_and_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    failed_index: int,
) -> None:
    repo = _repo(tmp_path)
    hosting = repo / "infra" / "hosting"
    hosting.mkdir(parents=True)
    (hosting / "uv.lock").write_text("lock\n")
    seen: list[tuple[str, ...]] = []

    def fake_run(
        argv: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == hosting
        assert timeout == 19
        assert env is None
        seen.append(argv)
        if len(seen) - 1 == failed_index:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, timeout)
            return subprocess.CompletedProcess(argv, 1, "detail\nfailed\n", "")
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", fake_run)
    assert main(["--cwd", str(repo), "--base", "HEAD", "--timeout", "19"]) == 1
    output = capsys.readouterr().out
    names = ("ruff-check", "ruff-format", "mypy", "pytest")
    last = "timeout" if failure == "timeout" else "failed"
    assert f"FAIL hosting:{names[failed_index]} {last}\n" in output
    if failure == "exit":
        assert "  detail\n  failed\n" in output
    assert output.endswith("RESULT FAIL\n")
    assert len(seen) == 4
    sha = _git(repo, "rev-parse", "HEAD").strip()
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["sha"] == sha
    assert data["base"] == sha
    assert [row["gate"] for row in data["gates"]] == list(names)
    assert all(row["area"] == "hosting" for row in data["gates"])
    assert [row["status"] for row in data["gates"]] == [
        "FAIL" if index == failed_index else "PASS" for index in range(4)
    ]
    assert data["gates"][failed_index]["last_line"] == last


def test_frontend_fail_does_not_stop_later_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        code = 1 if argv[:2] == ["npm", "run"] and argv[2:] == ["lint"] else 0
        return subprocess.CompletedProcess(argv, code, "x\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", inner)
    results = run_area_gates(tmp_path, {"frontend"}, 5)
    assert [gate for _, gate, _, _, _ in results] == [
        "npm-ci",
        "lint",
        "test",
        "build",
    ]
    assert [status for _, _, status, _, _ in results] == [
        "PASS",
        "FAIL",
        "PASS",
        "PASS",
    ]


def test_is_clean_rejects_untracked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert is_clean(repo) is True
    (repo / "untracked.txt").write_text("x\n")
    assert is_clean(repo) is False


def test_is_clean_rejects_tracked_changes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "keep.txt").write_text("changed\n")
    assert is_clean(repo) is False


def test_fail_run_writes_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route(1, "bad\n"))
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 1
    sha = _git(repo, "rev-parse", "HEAD").strip()
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["sha"] == sha
    assert data["gates"]
    assert any(row["status"] == "FAIL" for row in data["gates"])


def test_record_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", base]) == 0
    sha = _git(repo, "rev-parse", "HEAD").strip()
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["sha"] == sha
    assert data["base"] == base
    assert data["clean"] is True
    assert data["lines"] == 1
    assert isinstance(data["finished"], str)
    assert "T" in data["finished"]
    assert data["gates"]
    for row in data["gates"]:
        assert set(row) == {"area", "gate", "status", "last_line"}
        assert row["status"] == "PASS"
        assert row["area"] == "backend"


def test_reuse_hit_runs_no_gates_with_ignored_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(
        repo,
        sha,
        True,
        4,
        [("backend", "ruff-check", "PASS", "ok", ())],
        base=sha,
    )
    cached = load_reuse(repo, sha, True, base=sha)
    assert cached is not None
    (repo / ".fewia-supervisor-session").mkdir()
    (repo / ".fewia-supervisor-session" / "progress.md").write_text("running\n")
    (repo / "ignored").mkdir()
    (repo / "ignored" / "cache.py").write_text("cache\n")
    assert is_clean(repo) is True

    def never_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("_run_gate must not be called")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", never_run)
    assert main(["--cwd", str(repo), "--base", "main", "--reuse"]) == 0
    out = capsys.readouterr().out
    assert "REUSED PASS backend:ruff-check ok" in out
    assert "REUSED LINES 4/150" in out
    assert out.strip().endswith("RESULT PASS")


def test_reuse_miss_different_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(
        repo,
        sha,
        True,
        2,
        [("backend", "ruff-check", "PASS", "old", ())],
        base=sha,
    )
    (repo / "keep.txt").write_text("a\nb\n")
    _git(repo, "add", "keep.txt")
    _git(repo, "commit", "-m", "second")
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD", "--reuse"]) == 0
    assert "REUSED" not in capsys.readouterr().out


def test_reuse_miss_when_record_not_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(
        repo,
        sha,
        False,
        2,
        [("backend", "ruff-check", "PASS", "old", ())],
        base=sha,
    )
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD", "--reuse"]) == 0
    assert "REUSED" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps({"sha": "x", "clean": True, "lines": 1}),
        json.dumps(
            {
                "sha": "x",
                "clean": True,
                "lines": "4",
                "gates": [
                    {
                        "area": "backend",
                        "gate": "ruff-check",
                        "status": "PASS",
                        "last_line": "ok",
                    }
                ],
            }
        ),
        json.dumps({"sha": "x", "clean": True, "lines": 1, "gates": "nope"}),
        json.dumps(
            {
                "sha": "x",
                "clean": True,
                "lines": 1,
                "gates": [
                    {
                        "area": "backend",
                        "gate": "pytest",
                        "status": "UNKNOWN",
                        "last_line": "ok",
                    }
                ],
            }
        ),
    ],
)
def test_reuse_miss_malformed_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: str,
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        pass
    else:
        data.update(sha=sha, base=base)
        payload = json.dumps(data)
    record_dir = repo / ".fewia-supervisor-gates"
    record_dir.mkdir()
    (record_dir / f"{sha}.json").write_text(payload)
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", base, "--reuse"]) == 0
    assert "REUSED" not in capsys.readouterr().out


def test_reuse_miss_when_dirty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(
        repo,
        sha,
        True,
        2,
        [("backend", "ruff-check", "PASS", "old", ())],
        base=sha,
    )
    (repo / "keep.txt").write_text("dirty\n")
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD", "--reuse"]) == 0
    assert "REUSED" not in capsys.readouterr().out


def test_untracked_source_forces_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    argv = ["--cwd", str(repo), "--base", base, "--reuse"]
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(argv) == 0
    capsys.readouterr()
    (repo / "backend" / "new.py").write_text("new\n")
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route(0, "rerun\n"))
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "REUSED" not in out
    assert "PASS backend:pytest rerun" in out
    sha = _git(repo, "rev-parse", "HEAD").strip()
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["clean"] is False
    assert load_reuse(repo, sha, True, base=base) is None


def test_same_head_changed_base_invalidates_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "tag", "comparison", base)
    argv = ["--cwd", str(repo), "--base", "comparison", "--reuse"]
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(argv) == 0
    assert "LINES 1/150" in capsys.readouterr().out
    _git(repo, "tag", "-f", "comparison", sha)
    assert main(argv) == 0
    assert capsys.readouterr().out == "RESULT PASS (no gates for these paths)\n"
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["base"] == sha
    assert data["gates"] == []
    assert _git(repo, "rev-parse", "HEAD").strip() == sha


def test_base_alias_reuses_resolved_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    _git(repo, "tag", "comparison", base)
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route())
    assert main(["--cwd", str(repo), "--base", base]) == 0
    capsys.readouterr()
    assert main(["--cwd", str(repo), "--base", "comparison", "--reuse"]) == 0
    assert "REUSED PASS backend:pytest" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("field", "value"),
    [("base", None), ("sha", None), ("base", "wrong"), ("sha", "wrong")],
)
def test_reuse_rejects_missing_or_mismatched_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str | None,
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(
        repo, sha, True, 1, [("backend", "pytest", "PASS", "cached", ())], base=base
    )
    path = repo / ".fewia-supervisor-gates" / f"{sha}.json"
    data = json.loads(path.read_text())
    if value is None:
        del data[field]
    else:
        data[field] = value
    path.write_text(json.dumps(data))
    assert is_clean(repo) is True
    assert load_reuse(repo, sha, True, base=base) is None
    monkeypatch.setattr("dev_supervisor.gates._run_gate", _route(0, "rerun\n"))
    assert main(["--cwd", str(repo), "--base", base, "--reuse"]) == 0
    out = capsys.readouterr().out
    assert "REUSED" not in out
    assert "PASS backend:pytest rerun" in out


@pytest.mark.parametrize(
    "change", ["tracked", "untracked", "head", "unrelated-head", "missing-head"]
)
def test_snapshot_change_during_gates_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    change: str,
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    sha = _git(repo, "rev-parse", "HEAD").strip()

    def change_snapshot(*args: object, **kwargs: object) -> list[GateRow]:
        if change == "tracked":
            (repo / "backend" / "x.py").write_text("changed\n")
        elif change == "untracked":
            (repo / "backend" / "new.py").write_text("new\n")
        elif change == "head":
            _git(repo, "commit", "--allow-empty", "-m", "Advance HEAD")
        elif change == "unrelated-head":
            _git(repo, "checkout", "--orphan", "unrelated")
            _git(repo, "commit", "-m", "Create unrelated root")
        else:
            _git(repo, "update-ref", "-d", "refs/heads/main")
        return [("backend", "pytest", "PASS", "ok", ())]

    monkeypatch.setattr("dev_supervisor.gates.run_area_gates", change_snapshot)
    assert main(["--cwd", str(repo), "--base", base]) == 1
    out = capsys.readouterr().out
    assert "FAIL snapshot:source source changed during gates" in out
    assert out.endswith("RESULT FAIL\n")
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["sha"] == sha
    assert data["base"] == base
    assert data["clean"] is False
    assert data["gates"][-1]["status"] == "FAIL"
    assert load_reuse(repo, sha, True, base=base) is None
    if change in {"head", "unrelated-head"}:
        new_sha = _git(repo, "rev-parse", "HEAD").strip()
        assert new_sha != sha
        assert not (repo / ".fewia-supervisor-gates" / f"{new_sha}.json").exists()


def test_dirty_snapshot_stays_nonreusable_when_gates_clean_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    base = _commit_backend(repo)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    source = repo / "backend" / "x.py"
    source.write_text("dirty\n")

    def clean_snapshot(*args: object, **kwargs: object) -> list[GateRow]:
        source.write_text("a\n")
        return [("backend", "pytest", "PASS", "ok", ())]

    monkeypatch.setattr("dev_supervisor.gates.run_area_gates", clean_snapshot)
    assert main(["--cwd", str(repo), "--base", base]) == 0
    assert is_clean(repo) is True
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["clean"] is False
    assert load_reuse(repo, sha, True, base=base) is None


@pytest.mark.parametrize("reuse", [False, True])
def test_unknown_base_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reuse: bool
) -> None:
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    write_record(repo, sha, True, 0, [], base=sha)
    argv = ["--cwd", str(repo), "--base", "no-such-ref"]
    if reuse:
        argv.append("--reuse")
    assert main(argv) == 1
    out = capsys.readouterr().out
    assert out.startswith("RESULT FAIL (git: ")
    assert "RESULT PASS" not in out
    assert "REUSED" not in out


def test_rename_reports_old_and_new_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(_cwd: Path, *args: str) -> list[str]:
        if args[:2] == ("merge-base", "main"):
            return ["deadbeef"]
        if args[:3] == ("ls-files", "--others", "--exclude-standard"):
            return []
        if args[:3] == ("diff", "--name-only", "--no-renames"):
            return ["backend/old.py", "backend/new.py"]
        raise AssertionError(args)

    monkeypatch.setattr("dev_supervisor.gates._git", fake_git)
    assert changed_paths(tmp_path, "main") == {
        "backend/old.py",
        "backend/new.py",
    }


def test_untracked_counts_final_line_without_newline(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("one\ntwo")
    assert count_added_lines(repo, "HEAD") == 2


def test_compose_docker_missing_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[object] = []

    def never_run(*args: object, **kwargs: object) -> None:
        started.append(args)
        raise AssertionError("_run_gate must not start")

    monkeypatch.setattr("dev_supervisor.gates.shutil.which", lambda _name: None)
    monkeypatch.setattr("dev_supervisor.gates._run_gate", never_run)
    results = run_area_gates(tmp_path, {"compose"}, 5)
    assert results == [("compose", "config", "SKIP", "docker not found", ())]
    assert started == []


def test_npm_ci_skipped_when_node_modules_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    seen: list[list[str]] = []

    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", inner)
    results = run_area_gates(tmp_path, {"frontend"}, 5)
    assert [gate for _, gate, _, _, _ in results] == [
        "npm-ci",
        "lint",
        "test",
        "build",
    ]
    assert results[0][2:] == ("SKIP", "node_modules present", ())
    assert [status for _, _, status, _, _ in results[1:]] == ["PASS", "PASS", "PASS"]
    assert all(argv[:2] != ["npm", "ci"] for argv in seen)


def test_npm_ci_failure_skips_later_frontend_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[list[str]] = []

    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        started.append(argv)
        code = 1 if argv[:2] == ["npm", "ci"] else 0
        return subprocess.CompletedProcess(argv, code, "err\n", "")

    monkeypatch.setattr("dev_supervisor.gates._run_gate", inner)
    results = run_area_gates(tmp_path, {"frontend", "tools"}, 5)
    frontend = [row for row in results if row[0] == "frontend"]
    tools = [row for row in results if row[0] == "tools"]
    assert [gate for _, gate, _, _, _ in frontend] == [
        "npm-ci",
        "lint",
        "test",
        "build",
    ]
    assert frontend[0][2] == "FAIL"
    assert [status for _, _, status, last, _ in frontend[1:]] == [
        "SKIP",
        "SKIP",
        "SKIP",
    ]
    assert all(last == "npm ci failed" for _, _, _, last, _ in frontend[1:])
    assert all(status == "PASS" for _, _, status, _, _ in tools)
    assert tools
    assert all(
        argv[:2] != ["npm", "run"] and argv != ["npm", "test"] for argv in started
    )
