from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from pathlib import Path
from typing import IO, Any, cast

from dev_supervisor.process import stop
from dev_supervisor.usage import add_counts, ledger_path, parse_codex_usage, write_usage

REVIEW_DEFAULT = {"grok-4.6": "gpt-6-luna", "gpt-5.3-codex-spark": "gpt-6-luna"}
REVIEW_DEFAULT["gpt-6-luna"] = "gpt-6-sol"
REVIEW_DEFAULT["gpt-6-sol"] = "gpt-6-luna"
EFFORT = {"simple": "low", "standard": "medium", "complex": "high"}
EFFORT.update(exceptional="high", maximum="high")
GUARD, FORMAT = (
    "Do not modify files. Do not run tests, package managers, or commands\n"
    "that write. The coordinator ran the gates; their record follows when\n"
    "provided.",
    "End the review with exactly one line, and no other line matching this\n"
    "pattern: VERDICT: APPROVE or VERDICT: REQUEST_CHANGES or\n"
    "VERDICT: BLOCKED.",
)


def parse_stdout(raw: bytes) -> dict[str, int | None] | None:
    totals: dict[str, int | None] | None = None
    for line in raw.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = None
        if isinstance(event, dict):
            usage = parse_codex_usage(cast(dict[str, Any], event))
            totals = add_counts(totals, usage) if usage is not None else totals
    return totals


def run_codex(
    args: list[str], cwd: Path, stdin: IO[bytes], timeout: float
) -> tuple[bytes, bool, int]:
    started = time.monotonic()
    opts: dict[str, Any] = {"cwd": cwd, "stdin": stdin, "stdout": subprocess.PIPE}
    opts["stderr"] = subprocess.STDOUT
    opts["start_new_session"] = True
    process = subprocess.Popen(args, **opts)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(process)
        stdout, _ = process.communicate()
        return stdout or b"", True, int((time.monotonic() - started) * 1000)
    return stdout or b"", False, int((time.monotonic() - started) * 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("--cwd", "--base", "--brief", "--writer-model"):
        parser.add_argument(name, required=True)
    parser.add_argument("--complexity", required=True, choices=tuple(EFFORT))
    for opt in ("--model", "--work-item", "--gates-file"):
        parser.add_argument(opt)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    cwd = Path(args.cwd).resolve()

    def git(*flags: str) -> str:
        return subprocess.check_output(["git", *flags], cwd=cwd, text=True)

    if git("status", "--porcelain", "--untracked-files=no"):
        print("Tracked tree is dirty", file=sys.stderr)
        raise SystemExit(2)
    brief = Path(args.brief)
    if not brief.is_file():
        print("Brief file not found", file=sys.stderr)
        raise SystemExit(2)
    if args.model is not None and args.model == args.writer_model:
        print("Review model MUST NOT equal writer model", file=sys.stderr)
        raise SystemExit(2)
    model = args.model or REVIEW_DEFAULT.get(args.writer_model, "gpt-6-luna")
    effort = EFFORT[args.complexity]
    sha = git("rev-parse", "HEAD").strip()
    root = Path(git("rev-parse", "--show-toplevel").strip())
    if args.gates_file is not None:
        gates: str | None = Path(args.gates_file).read_text()
    else:
        path = root / ".fewia-supervisor-gates" / f"{sha}.json"
        gates = path.read_text() if path.is_file() else None
    role = tomllib.loads((root / ".codex/agents/code-reviewer.toml").read_text())
    parts = [str(role["developer_instructions"]), GUARD]
    parts += [f"Review range: {args.base}...{sha}", brief.read_text()]
    if gates is not None:
        parts.append("Gates:\n" + gates)
    parts.append(FORMAT)
    dest = root / ".fewia-supervisor-reviews" / f"{sha}-{model}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    cmd = ["codex", "exec", "--model", model, "--cd", str(cwd)]
    cmd += ["--sandbox", "read-only", "--ephemeral", "--ignore-user-config", "--json"]
    cmd += ["-c", f'model_reasoning_effort="{effort}"', "-o", str(dest), "-"]
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompt_path = Path(tmp_dir) / "prompt.txt"
        prompt_path.write_text("\n".join(parts))
        with prompt_path.open("rb") as source:
            raw, timed_out, elapsed_ms = run_codex(cmd, cwd, source, args.timeout)
    totals = parse_stdout(raw)
    if not dest.exists() or dest.stat().st_size == 0:
        reason = "timed out" if timed_out else "produced no output"
        dest.write_text(f"No review report. codex {reason}.\n")
    message = dest.read_text()
    verdict, found = "BLOCKED", False
    for line in message.splitlines():
        if line in ("VERDICT: APPROVE", "VERDICT: REQUEST_CHANGES", "VERDICT: BLOCKED"):
            verdict, found = line.split()[1], True
    outcome = "timeout" if timed_out else "completed" if found else "task_failed"
    lines = message.splitlines()
    extra = f"\n... truncated, full text: {dest}" if len(lines) > 60 else ""
    print("\n".join(lines[:60]) + extra)
    inn = None if totals is None else totals["input_tokens"]
    body = dict(verdict=verdict, model=model, effort=effort, sha=sha)
    body.update(elapsed_ms=elapsed_ms, saved=str(dest), input_tokens=inn)
    body["output_tokens"] = None if totals is None else totals["output_tokens"]
    print(json.dumps(body))
    meta: dict[str, Any] = {"provenance": "none"}
    if totals is not None:
        meta = {"provenance": "codex.turn.completed", **totals}
    rec = [ledger_path(cwd), str(uuid.uuid4()), args.work_item, "review", "codex"]
    write_usage(*cast(Any, rec + [model, effort, outcome, meta, elapsed_ms]))
    raise SystemExit({"APPROVE": 0, "REQUEST_CHANGES": 1}.get(verdict, 2))


if __name__ == "__main__":
    main()
