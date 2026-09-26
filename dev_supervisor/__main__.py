from __future__ import annotations

import argparse
import json
import math
import subprocess
import tomllib
import uuid
from pathlib import Path
from typing import Any

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
from dev_supervisor.process import attempt, publish
from dev_supervisor.usage import (
    ledger_path,
    phase_name,
    token,
    work_item_id,
    write_usage,
)

GUARD = """
Use assigned files only. Preserve all changes. Follow AGENTS.md hard rules.
Use the bounded task brief and targeted integration context. Explore alternatives
within the given scope. Query graphs on demand; report missing relevant context.
Do not spawn agents, detach processes, merge, push, or change global settings.
Do not perform external mutations. Return external actions to the coordinator.
Do not read credentials or include secrets in prompts, logs, or checkpoints.
You MUST NOT run shell commands, tests, package managers, or git commands.
Edit only the assigned files. The coordinator runs all verification and records
the results.
This rule overrides any role or assignment text that asks you to run checks;
record the checks you would run as remaining work in progress.md.
Update progress.md after each completed edit and before changing work stages.
Record edits made, remaining work, and uncertain operations. On handoff read
the owned files first. Do not repeat an uncertain external action. A separate
Codex or Grok agent independently verifies the result.
"""


def _record_attempt(
    cwd: Path,
    state: Path,
    attempt_id: str,
    work_item: str | None,
    phase: str | None,
    provider: str,
    model: str,
    resolved: str | None,
    result: str,
) -> None:
    meta: dict[str, Any] = {}
    usage_file = state / "usage.json"
    if usage_file.is_file():
        try:
            loaded = json.loads(usage_file.read_text())
        except (OSError, ValueError, TypeError):
            loaded = None
        if isinstance(loaded, dict):
            meta = loaded
    elapsed_ms = token(meta.get("elapsed_ms")) or 0
    try:
        write_usage(
            ledger_path(cwd),
            attempt_id,
            work_item,
            phase,
            provider,
            model,
            resolved,
            result,
            meta,
            elapsed_ms,
        )
    except (OSError, ValueError, TypeError, subprocess.CalledProcessError):
        print("warning: usage ledger write failed", flush=True)


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
            + "\nInterrupted edits remain in this worktree. "
            "Read the owned files before you edit them.\n"
        )
        token = str(uuid.uuid4())
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
        history.append({"model": name, "outcome": result})
        (state / "result.json").write_text(json.dumps(history, indent=2))
        print(json.dumps(history[-1]), flush=True)
        _record_attempt(
            cwd,
            state,
            token,
            work_item,
            phase,
            models[name].provider,
            name,
            resolved,
            result,
        )
        if result not in RETRYABLE:
            return result
    return "all_providers_exhausted"


def dispatch(
    cwd: Path,
    task: Path,
    role: str,
    git_dir: Path,
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
    with lease(git_dir, cwd) as state:
        print(f"Private checkpoint directory: {state}", flush=True)
        try:
            result = execute(
                cwd,
                task,
                role,
                state,
                models,
                sequence,
                idle,
                limit,
                complexity,
                effort,
                files,
                work_item,
                phase,
            )
        except Exception:  # noqa: BLE001
            if not (state / "status.json").exists():
                publish(state, {"state": "stopped"})
            raise
        print(result, flush=True)
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--complexity", required=True, choices=tuple(COMPLEXITY))
    parser.add_argument("--effort", choices=EFFORTS)
    parser.add_argument("--model")
    parser.add_argument("--only", action="store_true")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--idle-seconds", type=float, default=180)
    parser.add_argument("--limit-seconds", type=float, default=3600)
    parser.add_argument("--write-file", action="append", default=[], metavar="PATH")
    parser.add_argument("--work-item")
    parser.add_argument("--phase", choices=("implement", "repair"))
    args = parser.parse_args()
    cwd = args.cwd.resolve()
    if not all(
        math.isfinite(n) and n > 0 for n in (args.idle_seconds, args.limit_seconds)
    ):
        parser.error("Time bounds must be positive")
    if Path(args.role).name != args.role:
        parser.error("Role must be a file stem")
    if not args.task.is_file():
        parser.error("--task takes a file path, not inline text")
    role_file = cwd / ".codex/agents" / f"{args.role}.toml"
    if not role_file.is_file():
        parser.error(f"Missing role file: {role_file}")
    work_item: str | None = None
    phase: str | None = None
    try:
        if args.work_item is not None:
            work_item = work_item_id(args.work_item)
        if args.phase is not None:
            phase = phase_name(args.phase)
    except ValueError as error:
        parser.error(str(error))
    models = dict(MODELS)
    try:
        if args.registry:
            models = load_registry(tomllib.loads(args.registry.read_text()))
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
    result = dispatch(
        cwd,
        args.task,
        args.role,
        git_dir,
        models,
        sequence,
        args.idle_seconds,
        args.limit_seconds,
        args.complexity,
        args.effort,
        authorized,
        work_item,
        phase,
    )
    raise SystemExit(0 if result == "completed" else 1)


if __name__ == "__main__":
    main()
