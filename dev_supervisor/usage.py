from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
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


def group_coverage(coverages: list[str], known_counts: int) -> str:
    if coverages and all(item == "unsupported" for item in coverages):
        return "unsupported"
    if coverages and all(item == "complete" for item in coverages):
        return "complete"
    if known_counts == 0:
        return "unknown"
    return "partial"


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


def ledger_path(cwd: Path) -> Path:
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=cwd, text=True
    ).strip()
    root = Path(common)
    if not root.is_absolute():
        root = cwd / root
    return root.resolve() / LEDGER


def summarize(rows: list[dict[str, Any]]) -> list[str]:
    groups: dict[tuple[object, object], list[dict[str, Any]]] = {}
    order: list[tuple[object, object]] = []
    lines: list[str] = []
    for row in rows:
        key = (row.get("work_item"), row.get("phase"))
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(row)
    for work, phase in order:
        bucket = groups[(work, phase)]
        elapsed = 0
        totals: dict[str, int | None] | None = None
        run_coverages: list[str] = []
        no_tokens = 0
        known_counts = 0
        for entry in bucket:
            if not isinstance(entry, dict):
                no_tokens += 1
                run_coverages.append("unknown")
                continue
            raw = token(entry.get("elapsed_ms"))
            elapsed += 0 if raw is None else raw
            counts = {name: token(entry.get(name)) for name in COUNTS}
            known = sum(value is not None for value in counts.values())
            known_counts += known
            if known == 0:
                no_tokens += 1
            provenance = entry.get("provenance")
            source = provenance if isinstance(provenance, str) else "none"
            run_coverages.append(coverage(counts, source))
            if known:
                totals = add_counts(totals, counts)
        inn: int | None
        out: int | None
        cov = group_coverage(run_coverages, known_counts)
        if totals is None:
            inn, out = None, None
        else:
            inn = totals["input_tokens"]
            out = totals["output_tokens"]
        seconds = elapsed / 1000
        sec = str(int(seconds)) if seconds == int(seconds) else str(seconds)
        work_text = "-" if work is None else str(work)
        phase_text = "-" if phase is None else str(phase)
        inn_text = "n/a" if inn is None else str(inn)
        out_text = "n/a" if out is None else str(out)
        extra = f" no_tokens={no_tokens}" if no_tokens else ""
        lines.append(
            f"{work_text} {phase_text} runs={len(bucket)} elapsed_s={sec} "
            f"input={inn_text} output={out_text} coverage={cov}{extra}"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-item")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()
    item: str | None = None
    if args.work_item is not None:
        try:
            item = work_item_id(args.work_item)
        except ValueError as error:
            parser.error(str(error))
    path = ledger_path(args.cwd.resolve())
    rows: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                loaded = json.loads(line)
            except ValueError:
                continue
            if isinstance(loaded, dict) and (
                item is None or loaded.get("work_item") == item
            ):
                rows.append(loaded)
    if not rows:
        print("No usage recorded.")
        return
    for line in summarize(rows):
        print(line)


if __name__ == "__main__":
    main()
