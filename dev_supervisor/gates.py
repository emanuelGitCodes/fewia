# ruff: noqa: E302, E305, E701, E702
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

RECORD_DIR = ".fewia-supervisor-gates"
EXCLUDE = re.compile(
    r"(^|/)(tests?|__tests__|vendor|dist|build|node_modules|artifacts)/"
    r"|\.(test|spec)\.[jt]sx?$|\.(md|lock|snap)$|-lock\.json$"
)
# fmt: off
_SRC = """\
backend|ruff-check|backend|uv run ruff check app tests|
backend|ruff-format|backend|uv run ruff format --check app tests|
backend|mypy|backend|uv run mypy --strict app|
backend|pytest|backend|uv run pytest -q|
frontend|npm-ci|frontend|npm ci --ignore-scripts|
frontend|lint|frontend|npm run lint|
frontend|test|frontend|npm test|
frontend|build|frontend|npm run build|
tools|pytest||uv run --project backend pytest -q tests/supervisor tests/infra|p
tools|ruff-check||uv run --project backend ruff check dev_supervisor tests infra --exclude infra/bedrock|p
tools|ruff-format||uv run --project backend ruff format --check dev_supervisor tests infra --exclude infra/bedrock|p
tools|mypy||uv run --project backend mypy --strict dev_supervisor infra/bedrock_session.py infra/floci_bootstrap.py|p
cdk|pytest|infra/bedrock|uv run pytest -q|
cdk|ruff-check|infra/bedrock|uv run ruff check .|
cdk|ruff-format|infra/bedrock|uv run ruff format --check .|
cdk|mypy|infra/bedrock|uv run mypy --strict .|
compose|config||docker compose config --quiet|
"""
GATES = tuple((a, g, d, tuple(c.split()), (("PYTHONPATH", "."),) if m else ()) for a, g, d, c, m in (ln.split("|") for ln in _SRC.strip().splitlines()))

@dataclass(frozen=True)
class GateResult:
    area: str
    gate: str
    status: str
    last_line: str
    tail: tuple[str, ...]

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout

def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line]

def changed_paths(cwd: Path, base: str) -> set[str]:
    merge = _git(cwd, "merge-base", base, "HEAD").strip()
    return set(_lines(_git(cwd, "diff", "--name-only", merge))) | set(_lines(_git(cwd, "ls-files", "--others", "--exclude-standard")))

def areas_for(paths: set[str]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        if path.startswith("infra/bedrock/"): found.add("cdk")
        elif path.startswith("backend/"): found.add("backend")
        elif path.startswith("frontend/"): found.add("frontend")
        elif path.startswith(("dev_supervisor/", "tests/")) or path == "ruff.toml" or (path.startswith("infra/") and path.endswith(".py")): found.add("tools")
        elif "/" not in path and fnmatch.fnmatch(path, "compose*.yaml"): found.add("compose")
    return found

def count_added_lines(cwd: Path, base: str) -> int:
    merge = _git(cwd, "merge-base", base, "HEAD").strip()
    total = 0
    for row in _lines(_git(cwd, "diff", "--numstat", merge)):
        added, _, path = row.split("\t", 2)
        if added != "-" and EXCLUDE.search(path) is None: total += int(added)
    for path in _lines(_git(cwd, "ls-files", "--others", "--exclude-standard")):
        if EXCLUDE.search(path) is not None: continue
        try: parts = (cwd / path).read_text(encoding="utf-8", errors="ignore").split("\n")
        except OSError: continue
        total += len(parts) - (1 if parts and parts[-1] == "" else 0)
    return total

def is_clean(cwd: Path) -> bool:
    return _git(cwd, "status", "--porcelain", "--untracked-files=no") == ""

def run_area_gates(cwd: Path, areas: set[str], timeout: float) -> list[GateResult]:
    results: list[GateResult] = []
    for area, gate, suffix, argv, extra in GATES:
        if area not in areas or (gate == "npm-ci" and (cwd / "frontend" / "node_modules").exists()): continue
        if gate == "config" and shutil.which("docker") is None:
            results.append(GateResult(area, gate, "SKIP", "docker not on PATH", ())); continue
        try:
            done = subprocess.run(list(argv), cwd=cwd / suffix if suffix else cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=os.environ | dict(extra) if extra else None)
        except subprocess.TimeoutExpired:
            results.append(GateResult(area, gate, "FAIL", "timeout", ())); continue
        lines = _lines(done.stdout or "")
        status = "PASS" if done.returncode == 0 else "FAIL"
        results.append(GateResult(area, gate, status, lines[-1][:120] if lines else "", tuple(lines[-20:])))
    return results

def format_output(results: list[GateResult], lines: int, areas: set[str]) -> str:
    if not areas: return "RESULT PASS (no gates for these paths)\n"
    chunks: list[str] = []
    failed = False
    for item in results:
        chunks.append(f"{item.status} {item.area}:{item.gate} {item.last_line}")
        if item.status == "FAIL": failed = True; chunks.extend(f"  {line}" for line in item.tail)
    chunks += [f"LINES {lines}/150", "RESULT FAIL" if failed else "RESULT PASS"]
    return "\n".join(chunks) + "\n"

def write_record(cwd: Path, sha: str, clean: bool, lines: int, results: list[GateResult]) -> None:
    (cwd / RECORD_DIR).mkdir(parents=True, exist_ok=True)
    gates = [{"area": i.area, "gate": i.gate, "status": i.status, "last_line": i.last_line} for i in results]
    payload = {"sha": sha, "clean": clean, "lines": lines, "finished": datetime.now(UTC).isoformat(), "gates": gates}
    (cwd / RECORD_DIR / f"{sha}.json").write_text(json.dumps(payload))

def load_reuse(cwd: Path, sha: str, clean: bool) -> str | None:
    path = cwd / RECORD_DIR / f"{sha}.json"
    if not clean or not path.is_file(): return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("clean") is not True: return None
    results = [GateResult(g["area"], g["gate"], g["status"], g["last_line"], ()) for g in data.get("gates", [])]
    text = format_output(results, int(data["lines"]), {i.area for i in results})
    return "\n".join(ln if ln.startswith("RESULT") else f"REUSED {ln}" for ln in text.splitlines()) + "\n"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--timeout", type=float, default=900)
    ns = parser.parse_args(argv)
    cwd: Path = ns.cwd
    sha = _git(cwd, "rev-parse", "HEAD").strip()
    clean = is_clean(cwd)
    if ns.reuse:
        reused = load_reuse(cwd, sha, clean)
        if reused is not None: print(reused, end=""); return int(reused.splitlines()[-1] == "RESULT FAIL")
    areas = areas_for(changed_paths(cwd, ns.base))
    results = run_area_gates(cwd, areas, ns.timeout) if areas else []
    added = count_added_lines(cwd, ns.base) if areas else 0
    print(format_output(results, added, areas), end="")
    write_record(cwd, sha, clean, added, results)
    return int(any(item.status == "FAIL" for item in results))

if __name__ == "__main__":
    raise SystemExit(main())
