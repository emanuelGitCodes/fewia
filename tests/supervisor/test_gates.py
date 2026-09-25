import json
import subprocess
from pathlib import Path

import pytest

from dev_supervisor.gates import (
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
    _git(repo, "add", "keep.txt")
    _git(repo, "commit", "-m", "init")
    return repo


def _route(code: int = 0, output: str = "ok\n") -> object:
    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        if argv and argv[0] == "git":
            return _REAL_RUN(
                argv, cwd=kwargs.get("cwd"), capture_output=True, text=True
            )
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


def test_area_docs_only() -> None:
    paths = {
        "docs/plan.md",
        "wiki/log.md",
        "README.md",
        ".github/a.yml",
    }
    assert areas_for(paths) == set()


def test_area_compose() -> None:
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
            ("compose", "config", "SKIP", "docker not on PATH", ()),
            ("backend", "mypy", "PASS", "", ()),
        ],
        12,
        {"backend", "compose"},
    )
    assert text.splitlines() == [
        "PASS backend:ruff-check All checks passed!",
        "SKIP compose:config docker not on PATH",
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
    def boom(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["uv"], timeout=1)

    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", boom)
    results = run_area_gates(tmp_path, {"backend"}, 1.0)
    _, _, status, last_line, tail = results[0]
    assert status == "FAIL"
    assert last_line == "timeout"
    assert tail == ()


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
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 0
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route(1, "bad\n"))
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 1


def test_frontend_runs_lint_test_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
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

    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", inner)
    run_area_gates(tmp_path, {"tools"}, 5)
    assert seen
    for env in seen:
        assert isinstance(env, dict)
        assert env["PYTHONPATH"] == "."


def test_frontend_fail_does_not_stop_later_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0]
        assert isinstance(cmd, list | tuple)
        argv = [str(part) for part in cmd]
        code = 1 if argv[:2] == ["npm", "run"] and argv[2:] == ["lint"] else 0
        return subprocess.CompletedProcess(argv, code, "x\n", "")

    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", inner)
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


def test_frontend_npm_ci_skipped_when_node_modules_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
    results = run_area_gates(tmp_path, {"frontend"}, 5)
    assert [gate for _, gate, _, _, _ in results] == ["lint", "test", "build"]


def test_compose_skip_without_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_docker(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("dev_supervisor.gates.shutil.which", no_docker)
    results = run_area_gates(tmp_path, {"compose"}, 5)
    assert results == [("compose", "config", "SKIP", "docker not on PATH", ())]


def test_is_clean_ignores_untracked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert is_clean(repo) is True
    (repo / "untracked.txt").write_text("x\n")
    assert is_clean(repo) is True
    (repo / "keep.txt").write_text("changed\n")
    assert is_clean(repo) is False


def test_record_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD"]) == 0
    sha = _git(repo, "rev-parse", "HEAD").strip()
    data = json.loads((repo / ".fewia-supervisor-gates" / f"{sha}.json").read_text())
    assert data["sha"] == sha
    assert data["clean"] is True
    assert data["lines"] == 1
    assert isinstance(data["finished"], str)
    assert "T" in data["finished"]
    assert data["gates"]
    for row in data["gates"]:
        assert set(row) == {"area", "gate", "status", "last_line"}
        assert row["status"] == "PASS"
        assert row["area"] == "backend"


def test_reuse_hit_makes_no_subprocess_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sha = "abc123"
    write_record(
        tmp_path,
        sha,
        True,
        4,
        [("backend", "ruff-check", "PASS", "ok", ())],
    )
    cached = load_reuse(tmp_path, sha, True)
    assert cached is not None

    def always_sha(*args: object, **kwargs: object) -> list[str]:
        return [sha]

    def always_clean(_cwd: Path) -> bool:
        return True

    def never_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess.run must not be called")

    monkeypatch.setattr("dev_supervisor.gates._git", always_sha)
    monkeypatch.setattr("dev_supervisor.gates.is_clean", always_clean)
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", never_run)
    assert main(["--cwd", str(tmp_path), "--base", "main", "--reuse"]) == 0
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
    )
    (repo / "keep.txt").write_text("a\nb\n")
    _git(repo, "add", "keep.txt")
    _git(repo, "commit", "-m", "second")
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD", "--reuse"]) == 0
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
    )
    (repo / "keep.txt").write_text("dirty\n")
    (repo / "backend").mkdir()
    (repo / "backend" / "x.py").write_text("a\n")
    monkeypatch.setattr("dev_supervisor.gates.subprocess.run", _route())
    assert main(["--cwd", str(repo), "--base", "HEAD", "--reuse"]) == 0
    assert "REUSED" not in capsys.readouterr().out
