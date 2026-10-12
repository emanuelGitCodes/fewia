from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

INJECT = frozenset("*?[](){},;!\n\r\t\0")


def _unsafe_rule_text(text: str) -> bool:
    return any(ch in INJECT or ch == "\\" for ch in text)


def _rule_path(path: Path) -> Path:
    resolved = path.resolve()
    if _unsafe_rule_text(str(resolved)):
        raise ValueError("Write path MUST stay a relative worktree file")
    if resolved.exists() and not resolved.is_file():
        raise ValueError("Write path MUST stay a relative worktree file")
    return resolved


def writes(cwd: Path, paths: list[str]) -> list[Path]:
    root = cwd.resolve()
    allowed: list[Path] = []
    for raw in paths:
        if not raw or Path(raw).is_absolute() or _unsafe_rule_text(raw):
            raise ValueError("Write path MUST stay a relative worktree file")
        candidate = _rule_path(root / raw)
        candidate.relative_to(root)
        allowed.append(candidate)
    return allowed


EFFORTS = ("low", "medium", "high", "xhigh", "max")
COMPLEXITY = {
    "simple": "low",
    "standard": "medium",
    "complex": "high",
    "exceptional": "xhigh",
    "maximum": "max",
}


@dataclass(frozen=True)
class Model:
    provider: str
    ceiling: str | None = None


MODELS = {
    "grok-4.6": Model("grok", "medium"),
    "gpt-5.3-codex-spark": Model("codex"),
    "gpt-6-luna": Model("codex", "max"),
    "gpt-6.1-sol": Model("codex", "max"),
    "claude-sonnet-5-5": Model("claude", "max"),
    "claude-opus-5-5": Model("claude", "max"),
}
ADVISORS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1")
DEFAULTS = tuple(MODELS)[:3]
RETRYABLE = {"unavailable", "quota", "rate_limit", "stalled"}
_REGISTRY_FIELDS = frozenset({"provider", "ceiling"})


def _registry_model(name: str, spec: object) -> Model:
    if name in MODELS:
        raise ValueError("Registry MUST NOT replace a built-in model ID")
    if not isinstance(spec, Mapping):
        raise TypeError("Registry model MUST be a table")
    if "effort" in spec:
        raise ValueError("Registry MUST use ceiling instead of effort")
    extra = [key for key in spec if key not in _REGISTRY_FIELDS]
    if extra:
        raise ValueError("Registry model accepts provider and optional ceiling only")
    provider = spec.get("provider")
    if not isinstance(provider, str) or provider == "":
        raise ValueError("Registry model MUST set provider")
    if "ceiling" not in spec:
        return Model(provider)
    ceiling = spec.get("ceiling")
    if not isinstance(ceiling, str) or ceiling not in EFFORTS:
        raise ValueError("Unknown model ceiling")
    return Model(provider, ceiling)


def load_registry(entries: Mapping[str, object]) -> dict[str, Model]:
    models = dict(MODELS)
    for name, spec in entries.items():
        models[name] = _registry_model(name, spec)
    return models


def resolve_effort(
    complexity: str, spec: Model, explicit: str | None = None
) -> str | None:
    if complexity not in COMPLEXITY or (
        explicit is not None and explicit not in EFFORTS
    ):
        raise ValueError("Unknown complexity or effort")
    if spec.ceiling is None:
        if explicit is not None:
            raise ValueError("Explicit effort requires a model effort ceiling")
        return None
    if spec.ceiling not in EFFORTS:
        raise ValueError("Unknown complexity or effort")
    requested = COMPLEXITY[complexity] if explicit is None else explicit
    if EFFORTS.index(requested) <= EFFORTS.index(spec.ceiling):
        return requested
    if explicit is not None:
        raise ValueError("Explicit effort exceeds model ceiling")
    return spec.ceiling


def _accepts_explicit_effort(spec: Model, explicit: str) -> bool:
    if explicit not in EFFORTS:
        raise ValueError("Unknown complexity or effort")
    if spec.ceiling is None:
        return False
    if spec.ceiling not in EFFORTS:
        raise ValueError("Unknown complexity or effort")
    return EFFORTS.index(explicit) <= EFFORTS.index(spec.ceiling)


def order(
    requested: str | None,
    only: bool,
    models: dict[str, Model],
    effort: str | None = None,
) -> list[str]:
    if only and requested is None:
        raise ValueError("--only requires --model")
    if requested is not None and requested not in models:
        raise ValueError("Unknown model; register its provider before execution")
    if requested is not None and effort is not None:
        spec = models[requested]
        if not _accepts_explicit_effort(spec, effort):
            if spec.ceiling is None:
                raise ValueError("Explicit effort requires a model effort ceiling")
            raise ValueError("Explicit effort exceeds model ceiling")
    first = [requested] if requested else []
    sequence = first if only else first + [m for m in DEFAULTS if m not in first]
    if effort is None:
        return sequence
    compatible = [
        name for name in sequence if _accepts_explicit_effort(models[name], effort)
    ]
    if not compatible:
        raise ValueError("No model accepts the explicit effort")
    return compatible


def environment(spec: Model, advisor: str | None) -> dict[str, str]:
    if spec.provider == "claude" and advisor is None:
        return {"CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1"}
    return {}


def command(
    model: str,
    spec: Model,
    cwd: Path,
    prompt: Path,
    files: list[Path] | None = None,
    effort: str | None = None,
    advisor: str | None = None,
    budget: float | None = None,
) -> list[str]:
    if (advisor is not None or budget is not None) and spec.provider != "claude":
        raise ValueError("Advisor and budget require the claude provider")
    if advisor is not None and advisor not in ADVISORS:
        raise ValueError("Unknown advisor")
    if spec.provider == "claude":
        args = [
            "claude",
            "-p",
            "--safe-mode",
            "--model",
            model,
            "--effort",
            effort or "medium",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--tools",
            "Read,Edit,Write,Glob,Grep",
            "--permission-mode",
            "default",
            "--permission-prompts",
            "none",
            "--max-turns",
            "30",
        ]
        if advisor is not None:
            args += ["--advisor", advisor]
        if budget is not None:
            args += ["--max-budget-usd", f"{budget:.2f}"]
        rules: list[str] = []
        for path in files or []:
            text = str(_rule_path(path))
            if " " in text:
                raise ValueError("Write path MUST stay a relative worktree file")
            rules.append(f"Edit(/{text})")
        return args + ["--allowedTools", *rules]
    if spec.provider == "grok":
        args = [
            str(Path.home() / ".grok/bin/grok"),
            "--model",
            model,
            "--reasoning-effort",
            effort or "medium",
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
        for path in files or []:
            rendered = _rule_path(path)
            args += ["--allow", f"Write({rendered})", "--allow", f"Edit({rendered})"]
        return args
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
    if effort and spec.ceiling is not None:
        args += ["-c", f'model_reasoning_effort="{effort}"']
    return args + ["-"]
