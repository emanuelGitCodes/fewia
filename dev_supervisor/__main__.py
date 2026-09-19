from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
import uuid
from pathlib import Path

import tomllib

from dev_supervisor.lease import lease
from dev_supervisor.policy import (
    COMPLEXITY,
    EFFORTS,
    MODELS,
    RETRYABLE,
    Model,
    command,
    load_registry,
    order,
    resolve_effort,
    writes,
)
from dev_supervisor.process import attempt, take_record
from dev_supervisor.usage import LEDGER, PHASES, summarize, work_item_id, write_usage

GUARD = """
Use assigned files only. Preserve all changes. Follow AGENTS.md hard rules.
Use the bounded task brief and targeted integration context. Explore alternatives
within the given scope. Query graphs on demand; report missing relevant context.
Do not spawn agents, detach processes, merge, push, or change global settings.
Do not perform external mutations. Return external actions to the coordinator.
Do not read credentials or include secrets in prompts, logs, or checkpoints.
Update progress.md after each completed check and before changing work stages.
Record completed checks, remaining work, and uncertain operations. Never claim
an unfinished check passed. On handoff inspect the working tree first. Do not
repeat an uncertain external action. A separate Codex or Grok agent independently verifies the result.
"""


def execute(
    cwd: Path,
    task: Path,
    role: str,
    state: Path,
    models: dict[str, Model],
    sequence: list[str],
    idle: float,
    limit: float,
    complexity: str,
    effort: str | None = None,
    files: list[Path] | None = None,
    work_item: str | None = None,
    phase: str | None = None,
) -> str:
    instructions = tomllib.loads((cwd / ".codex/agents" / f"{role}.toml").read_text())
    assignment = task.read_text()
    progress = state / "progress.md"
    if not progress.exists():
        progress.write_text(
            "Completed checks: none recorded.\nRemaining work: original assignment.\n"
        )
    history: list[dict[str, str]] = []
    for name in sequence:
        resolved = resolve_effort(complexity, models[name], effort)
        checkpoint = {
            "model": name,
            "provider": models[name].provider,
            "complexity": complexity,
            "effort": resolved or "CLI configured default",
            "worktree": str(cwd),
            "role": role,
            "attempts": history,
        }
        (state / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2))
        print(json.dumps(checkpoint), flush=True)
        prompt = state / "prompt.txt"
        prompt.write_text(
            GUARD
            + f"\nProgress file: {progress}\n"
            + instructions["developer_instructions"]
            + "\nAssignment:\n"
            + assignment
            + "\nCheckpoint:\n"
            + progress.read_text()
            + "\nInspect git status and diff; interrupted edits remain in this worktree.\n"
        )
        token = str(uuid.uuid4())
        take_record()
        started = time.monotonic()
        result = attempt(
            command(
                name,
                models[name],
                cwd,
                prompt,
                [*(files or []), progress],
                resolved,
            ),
            cwd,
            prompt,
            state,
            token,
            idle,
            limit,
        )
        elapsed = max(0, int((time.monotonic() - started) * 1000))
        write_usage(
            cwd / LEDGER,
            token,
            work_item,
            phase,
            models[name].provider,
            name,
            resolved,
            result,
            take_record(),
            elapsed,
        )
        history.append({"model": name, "outcome": result})
        (state / "result.json").write_text(json.dumps(history, indent=2))
        print(json.dumps(history[-1]), flush=True)
        if result not in RETRYABLE:
            return result
    return "all_providers_exhausted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path)
    parser.add_argument("--role")
    parser.add_argument("--usage-summary", action="store_true")
    parser.add_argument("--work-item")
    parser.add_argument("--phase", choices=tuple(sorted(PHASES)))
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--complexity", choices=tuple(COMPLEXITY))
    parser.add_argument("--effort", choices=EFFORTS)
    parser.add_argument("--model")
    parser.add_argument("--only", action="store_true")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--idle-seconds", type=float, default=180)
    parser.add_argument("--limit-seconds", type=float, default=3600)
    parser.add_argument("--write-file", action="append", default=[], metavar="PATH")
    args = parser.parse_args()
    cwd = args.cwd.resolve()
    if args.usage_summary:
        print(json.dumps(summarize(cwd / LEDGER), indent=2), flush=True)
        raise SystemExit(0)
    if args.task is None or args.role is None or args.complexity is None:
        parser.error("--task, --role, and --complexity are required")
    if not all(
        math.isfinite(n) and n > 0 for n in (args.idle_seconds, args.limit_seconds)
    ):
        parser.error("Time bounds must be positive")
    if Path(args.role).name != args.role:
        parser.error("Role must be a file stem")
    models = dict(MODELS)
    try:
        if args.registry:
            models = load_registry(tomllib.loads(args.registry.read_text()))
        work_item = None if args.work_item is None else work_item_id(args.work_item)
        authorized = writes(cwd, args.write_file)
        sequence = order(args.model, args.only, models, args.effort)
        for name in sequence:
            resolved = resolve_effort(args.complexity, models[name], args.effort)
            command(name, models[name], cwd, Path("unused"), authorized, resolved)
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    branch = subprocess.check_output(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=cwd,
        text=True,
    ).strip()
    if branch in {"main", "master"}:
        parser.error("Use an isolated task branch")
    git_dir = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--absolute-git-dir"],
            cwd=cwd,
            text=True,
        ).strip()
    )
    with lease(git_dir, cwd) as state:
        print(f"Private checkpoint directory: {state}", flush=True)
        result = execute(
            cwd,
            args.task,
            args.role,
            state,
            models,
            sequence,
            args.idle_seconds,
            args.limit_seconds,
            args.complexity,
            args.effort,
            authorized,
            work_item,
            args.phase,
        )
        print(result, flush=True)
        raise SystemExit(0 if result == "completed" else 1)


if __name__ == "__main__":
    main()
