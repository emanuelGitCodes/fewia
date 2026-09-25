import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

RECORD_DIR = ".fewia-supervisor-gates"
EXCLUDE = re.compile(
    r"(^|/)(tests?|__tests__|vendor|dist|build|node_modules|artifacts)/"
    r"|\.(test|spec)\.[jt]sx?$|\.(md|lock|snap)$|-lock\.json$"
)
UV_RUN = ("uv", "run")
UV_RUN_BACKEND = (*UV_RUN, "--project", "backend")
EXCLUDE_BEDROCK = ("--exclude", "infra/bedrock")
TOOLS_TARGETS = ("dev_supervisor", "tests", "infra")
PYTHONPATH_ENV = (("PYTHONPATH", "."),)
BACKEND_RUFF_CHECK = (*UV_RUN, "ruff", "check", "app", "tests")
BACKEND_RUFF_FORMAT = (*UV_RUN, "ruff", "format", "--check", "app", "tests")
CDK_RUFF_FORMAT = (*UV_RUN, "ruff", "format", "--check", ".")
COMPOSE_CONFIG = ("docker", "compose", "config", "--quiet")
TOOLS_PYTEST = UV_RUN_BACKEND + ("pytest", "-q", "tests/supervisor", "tests/infra")
TOOLS_RUFF_CHECK = UV_RUN_BACKEND + ("ruff", "check", *TOOLS_TARGETS, *EXCLUDE_BEDROCK)
TOOLS_RUFF_FORMAT = UV_RUN_BACKEND + (
    "ruff",
    "format",
    "--check",
    *TOOLS_TARGETS,
    *EXCLUDE_BEDROCK,
)
TOOLS_MYPY_HEAD = UV_RUN_BACKEND + ("mypy", "--strict", "dev_supervisor")
TOOLS_MYPY = TOOLS_MYPY_HEAD + ("infra/bedrock_session.py", "infra/floci_bootstrap.py")

GateRow = tuple[str, str, str, str, tuple[str, ...]]

GATES = (
    ("backend", "ruff-check", "backend", BACKEND_RUFF_CHECK, ()),
    ("backend", "ruff-format", "backend", BACKEND_RUFF_FORMAT, ()),
    ("backend", "mypy", "backend", (*UV_RUN, "mypy", "--strict", "app"), ()),
    ("backend", "pytest", "backend", (*UV_RUN, "pytest", "-q"), ()),
    ("frontend", "npm-ci", "frontend", ("npm", "ci", "--ignore-scripts"), ()),
    ("frontend", "lint", "frontend", ("npm", "run", "lint"), ()),
    ("frontend", "test", "frontend", ("npm", "test"), ()),
    ("frontend", "build", "frontend", ("npm", "run", "build"), ()),
    ("tools", "pytest", "", TOOLS_PYTEST, PYTHONPATH_ENV),
    ("tools", "ruff-check", "", TOOLS_RUFF_CHECK, PYTHONPATH_ENV),
    ("tools", "ruff-format", "", TOOLS_RUFF_FORMAT, PYTHONPATH_ENV),
    ("tools", "mypy", "", TOOLS_MYPY, PYTHONPATH_ENV),
    ("cdk", "pytest", "infra/bedrock", (*UV_RUN, "pytest", "-q"), ()),
    ("cdk", "ruff-check", "infra/bedrock", (*UV_RUN, "ruff", "check", "."), ()),
    ("cdk", "ruff-format", "infra/bedrock", CDK_RUFF_FORMAT, ()),
    ("cdk", "mypy", "infra/bedrock", (*UV_RUN, "mypy", "--strict", "."), ()),
    ("compose", "config", "", COMPOSE_CONFIG, ()),
)


def _git(cwd: Path, *args: str) -> list[str]:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return [line for line in done.stdout.splitlines() if line]


def changed_paths(cwd: Path, base: str) -> set[str]:
    merge = (_git(cwd, "merge-base", base, "HEAD") or [""])[0]
    extra = _git(cwd, "ls-files", "--others", "--exclude-standard")
    return set(_git(cwd, "diff", "--name-only", merge)) | set(extra)


def areas_for(paths: set[str]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        if path.startswith("infra/bedrock/"):
            found.add("cdk")
        elif path.startswith(("backend/", "frontend/")):
            found.add(path.split("/", 1)[0])
        elif path.startswith(("dev_supervisor/", "tests/")) or path == "ruff.toml":
            found.add("tools")
        elif path.startswith("infra/") and path.endswith(".py"):
            found.add("tools")
        elif "/" not in path and path.startswith("compose") and path.endswith(".yaml"):
            found.add("compose")
    return found


def count_added_lines(cwd: Path, base: str) -> int:
    merge = (_git(cwd, "merge-base", base, "HEAD") or [""])[0]
    total = 0
    for row in _git(cwd, "diff", "--numstat", merge):
        added, _, path = row.split("\t", 2)
        if added != "-" and EXCLUDE.search(path) is None:
            total += int(added)
    for path in _git(cwd, "ls-files", "--others", "--exclude-standard"):
        if EXCLUDE.search(path) is None:
            try:
                text = (cwd / path).read_text(encoding="utf-8", errors="ignore")
                total += text.count("\n")
            except OSError:
                continue
    return total


def is_clean(cwd: Path) -> bool:
    return _git(cwd, "status", "--porcelain", "--untracked-files=no") == []


def run_area_gates(cwd: Path, areas: set[str], timeout: float) -> list[GateRow]:
    out: list[GateRow] = []
    for area, gate, folder, argv, env in (row for row in GATES if row[0] in areas):
        if gate == "npm-ci" and (cwd / "frontend" / "node_modules").exists():
            continue
        if gate == "config" and shutil.which("docker") is None:
            out.append((area, gate, "SKIP", "docker not on PATH", ()))
            continue
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd / folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                env=os.environ | dict(env) if env else None,
            )
        except subprocess.TimeoutExpired:
            out.append((area, gate, "FAIL", "timeout", ()))
            continue
        lines = [line for line in (proc.stdout or "").splitlines() if line]
        status = "PASS" if proc.returncode == 0 else "FAIL"
        last = lines[-1][:120] if lines else ""
        out.append((area, gate, status, last, tuple(lines[-20:])))
    return out


def format_output(results: list[GateRow], lines: int, areas: set[str]) -> str:
    if not areas:
        return "RESULT PASS (no gates for these paths)\n"
    chunks: list[str] = []
    for area, gate, status, last_line, tail in results:
        chunks.append(f"{status} {area}:{gate} {last_line}")
        if status == "FAIL":
            chunks.extend(f"  {line}" for line in tail)
    failed = any(status == "FAIL" for _, _, status, _, _ in results)
    chunks += [f"LINES {lines}/150", "RESULT FAIL" if failed else "RESULT PASS"]
    return "\n".join(chunks) + "\n"


def write_record(
    cwd: Path, sha: str, clean: bool, lines: int, results: list[GateRow]
) -> None:
    (cwd / RECORD_DIR).mkdir(parents=True, exist_ok=True)
    gates = [
        dict(area=area, gate=gate, status=status, last_line=last_line)
        for area, gate, status, last_line, _ in results
    ]
    payload = dict(
        sha=sha,
        clean=clean,
        lines=lines,
        finished=datetime.now(UTC).isoformat(),
        gates=gates,
    )
    (cwd / RECORD_DIR / f"{sha}.json").write_text(json.dumps(payload))


def load_reuse(cwd: Path, sha: str, clean: bool) -> str | None:
    path = cwd / RECORD_DIR / f"{sha}.json"
    if not clean or not path.is_file():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("clean") is not True:
        return None
    results: list[GateRow] = [
        (row["area"], row["gate"], row["status"], row["last_line"], ())
        for row in data.get("gates", [])
    ]
    areas = {area for area, _, _, _, _ in results}
    text = format_output(results, int(data["lines"]), areas)
    reused = "\n".join(
        line if line.startswith("RESULT") else f"REUSED {line}"
        for line in text.splitlines()
    )
    return reused + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--timeout", type=float, default=900)
    ns = parser.parse_args(argv)
    sha = _git(ns.cwd, "rev-parse", "HEAD")[0]
    clean = is_clean(ns.cwd)
    if ns.reuse:
        reused = load_reuse(ns.cwd, sha, clean)
        if reused is not None:
            print(reused, end="")
            return int(reused.splitlines()[-1] == "RESULT FAIL")
    areas = areas_for(changed_paths(ns.cwd, ns.base))
    results = run_area_gates(ns.cwd, areas, ns.timeout) if areas else []
    added = count_added_lines(ns.cwd, ns.base) if areas else 0
    print(format_output(results, added, areas), end="")
    write_record(ns.cwd, sha, clean, added, results)
    return int(any(status == "FAIL" for _, _, status, _, _ in results))


if __name__ == "__main__":
    raise SystemExit(main())
