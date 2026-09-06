from __future__ import annotations

import argparse
import json
import math
import subprocess
import uuid
from pathlib import Path

import tomllib

from dev_supervisor.lease import lease
from dev_supervisor.policy import MODELS, RETRYABLE, Model, command, order, writes
from dev_supervisor.process import attempt

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
    files: list[Path] | None = None,
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
        checkpoint = {
            "model": name,
            "provider": models[name].provider,
            "effort": models[name].effort or "CLI configured default",
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
        result = attempt(
            command(name, models[name], cwd, prompt, [*(files or []), progress]),
            cwd,
            prompt,
            state,
            str(uuid.uuid4()),
            idle,
            limit,
        )
        history.append({"model": name, "outcome": result})
        (state / "result.json").write_text(json.dumps(history, indent=2))
        print(json.dumps(history[-1]), flush=True)
        if result not in RETRYABLE:
            return result
    return "all_providers_exhausted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--model")
    parser.add_argument("--only", action="store_true")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--idle-seconds", type=float, default=180)
    parser.add_argument("--limit-seconds", type=float, default=3600)
    parser.add_argument("--write-file", action="append", default=[], metavar="PATH")
    args = parser.parse_args()
    cwd = args.cwd.resolve()
    if not all(
        math.isfinite(n) and n > 0 for n in (args.idle_seconds, args.limit_seconds)
    ):
        parser.error("Time bounds must be positive")
    if Path(args.role).name != args.role:
        parser.error("Role must be a file stem")
    models = dict(MODELS)
    if args.registry:
        for name, spec in tomllib.loads(args.registry.read_text()).items():
            models[name] = Model(**spec)
    try:
        authorized = writes(cwd, args.write_file)
        sequence = order(args.model, args.only, models)
        for name in sequence:
            command(name, models[name], cwd, Path("unused"), authorized)
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
            authorized,
        )
        print(result, flush=True)
        raise SystemExit(0 if result == "completed" else 1)


if __name__ == "__main__":
    main()
