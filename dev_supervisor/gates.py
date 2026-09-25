import argparse
import os
import re
import subprocess
from pathlib import Path

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


def run_area_gates(cwd: Path, areas: set[str], timeout: float) -> list[GateRow]:
    out: list[GateRow] = []
    for area, gate, folder, argv, env in (row for row in GATES if row[0] in areas):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=float, default=900)
    ns = parser.parse_args(argv)
    areas = areas_for(changed_paths(ns.cwd, ns.base))
    results = run_area_gates(ns.cwd, areas, ns.timeout) if areas else []
    added = count_added_lines(ns.cwd, ns.base) if areas else 0
    print(format_output(results, added, areas), end="")
    return int(any(status == "FAIL" for _, _, status, _, _ in results))


if __name__ == "__main__":
    raise SystemExit(main())
