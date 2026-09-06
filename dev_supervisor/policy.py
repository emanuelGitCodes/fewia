from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Model:
    provider: str
    effort: str | None = None


MODELS = {
    "grok-4.6": Model("grok", "medium"),
    "gpt-5.3-codex-spark": Model("codex"),
    "gpt-5.6-luna": Model("codex", "xhigh"),
    "gpt-5.6-sol": Model("codex"),
}
DEFAULTS = tuple(MODELS)[:3]
RETRYABLE = {"unavailable", "quota", "rate_limit", "stalled"}


def order(requested: str | None, only: bool, models: dict[str, Model]) -> list[str]:
    if only and requested is None:
        raise ValueError("--only requires --model")
    if requested is not None and requested not in models:
        raise ValueError("Unknown model; register its provider before execution")
    first = [requested] if requested else []
    return first if only else first + [m for m in DEFAULTS if m not in first]


def command(model: str, spec: Model, cwd: Path, prompt: Path) -> list[str]:
    if spec.provider == "grok":
        return [
            str(Path.home() / ".grok/bin/grok"),
            "--model",
            model,
            "--reasoning-effort",
            spec.effort or "medium",
            "--cwd",
            str(cwd),
            "--prompt-file",
            str(prompt),
            "--output-format",
            "streaming-json",
            "--max-turns",
            "30",
            "--no-subagents",
            "--permission-mode",
            "default",
        ]
    if spec.provider != "codex":
        raise ValueError("Provider needs a command and event adapter")
    args = [
        "codex",
        "exec",
        "--model",
        model,
        "--cd",
        str(cwd),
        "--json",
        "--sandbox",
        "workspace-write",
        "--add-dir",
        str(prompt.parent),
        "--ephemeral",
        "--ignore-user-config",
        "--disable",
        "multi_agent",
    ]
    if spec.effort:
        args += ["-c", f'model_reasoning_effort="{spec.effort}"']
    return args + ["-"]
