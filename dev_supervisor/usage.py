from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path
from typing import IO, Any

LEDGER = ".fewia-supervisor-usage.jsonl"
PHASES = frozenset({"implement", "review", "repair"})
WORK_ITEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
COUNTS = ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")
CODEX_KEYS = {
    "input_tokens": "input_tokens",
    "cached_tokens": "cached_input_tokens",
    "output_tokens": "output_tokens",
    "reasoning_tokens": "reasoning_output_tokens",
}


def work_item_id(value: str) -> str:
    if WORK_ITEM.fullmatch(value) is None:
        raise ValueError("Work item ID MUST match the supervisor identifier pattern")
    return value


def phase_name(value: str) -> str:
    if value not in PHASES:
        raise ValueError("Phase MUST be implement, review, or repair")
    return value


def token(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def fingerprint(event: dict[str, Any]) -> str | None:
    for key in ("turn_id", "id"):
        ident = event.get(key)
        if isinstance(ident, str) and ident:
            return ident
    return None


def parse_codex_usage(event: dict[str, Any]) -> dict[str, int | None] | None:
    if event.get("type") != "turn.completed":
        return None
    raw = event.get("usage")
    if not isinstance(raw, dict):
        return dict.fromkeys(COUNTS)
    return {
        name: token(raw[key]) if key in raw else None
        for name, key in CODEX_KEYS.items()
    }


def add_counts(
    totals: dict[str, int | None] | None, incoming: dict[str, int | None]
) -> dict[str, int | None]:
    if totals is None:
        return {name: incoming.get(name) for name in COUNTS}
    return {
        name: None
        if totals.get(name) is None or incoming.get(name) is None
        else int(totals[name] or 0) + int(incoming[name] or 0)
        for name in COUNTS
    }


def coverage(usage: dict[str, int | None] | None, provenance: str) -> str:
    if provenance == "unsupported":
        return "unsupported"
    known = 0 if usage is None else sum(value is not None for value in usage.values())
    return "complete" if known == len(COUNTS) else "partial" if known else "unknown"


def _ledger_file(path: Path) -> IO[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("Usage ledger MUST NOT be a symlink")
    if path.exists() and not path.is_file():
        raise OSError("Usage ledger MUST be a regular file")
    fd = os.open(
        os.fspath(path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        os.close(fd)
        raise
    return os.fdopen(fd, "a", encoding="utf-8")


def write_usage(
    path: Path,
    attempt_id: str,
    work_item: str | None,
    phase: str | None,
    provider: str,
    model: str,
    effort: str | None,
    outcome: str,
    meta: dict[str, Any],
    elapsed_ms: int,
) -> None:
    grok = provider == "grok"
    parsed = meta.get("provenance") == "codex.turn.completed" and not grok
    tokens = {name: token(meta.get(name)) if parsed else None for name in COUNTS}
    if grok:
        provenance = "unsupported"
    elif isinstance(meta.get("provenance"), str):
        provenance = str(meta["provenance"])
    else:
        provenance = "none"
    elapsed = token(elapsed_ms)
    if elapsed is None:
        elapsed = token(meta.get("elapsed_ms"))
    row = {
        "id": attempt_id,
        "work_item": work_item,
        "phase": phase,
        "provider": provider,
        "model": model,
        "effort": effort,
        "outcome": outcome,
        "elapsed_ms": 0 if elapsed is None else elapsed,
        **tokens,
        "provenance": provenance,
        "coverage": coverage(tokens, provenance),
    }
    text = json.dumps(row, separators=(",", ":"))
    with _ledger_file(path) as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def summarize(path: Path) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item: Any = json.loads(line) if line.strip() else None
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            raw_provider = item.get("provider")
            if not isinstance(raw_provider, str) or raw_provider == "":
                continue
            provider: str = raw_provider
            raw_work = item.get("work_item")
            work: str = raw_work if isinstance(raw_work, str) else ""
            bucket = groups.setdefault(
                (work, provider),
                {
                    "work_item": work or None,
                    "provider": provider,
                    "attempts": 0,
                    "repairs": 0,
                    **dict.fromkeys(COUNTS, 0),
                    **{f"{name}_unknown": 0 for name in COUNTS},
                    "known_token_totals_only": True,
                },
            )
            bucket["attempts"] += 1
            bucket["repairs"] += int(item.get("phase") == "repair")
            for name in COUNTS:
                value = token(item.get(name))
                if value is None:
                    bucket[f"{name}_unknown"] += 1
                else:
                    bucket[name] += value
    for bucket in groups.values():
        attempts = int(bucket["attempts"])
        for name in COUNTS:
            if int(bucket[f"{name}_unknown"]) == attempts:
                bucket[name] = None
    rows = sorted(
        groups.values(),
        key=lambda item: (str(item["work_item"] or ""), str(item["provider"])),
    )
    return {
        "groups": rows,
        "excluded": ["astra", "native"],
        "tokens_are_not_money_or_quota": True,
        "known_token_totals_are_not_spend": True,
    }
