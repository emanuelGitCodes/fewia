from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

LEDGER = ".fewia-supervisor-usage.jsonl"
PHASES = frozenset({"implement", "review", "repair", "coordinate", "junior"})
WORK_ITEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
COUNTS = ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")
CODEX_PROVENANCE = "codex.turn.completed"
GROK_PROVENANCE = "grok.end"
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
        raise ValueError(
            "Phase MUST be implement, review, repair, coordinate, or junior"
        )
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


def parse_grok_usage(event: dict[str, Any]) -> dict[str, int | None] | None:
    if event.get("type") != "end":
        return None
    raw = event.get("usage")
    if not isinstance(raw, dict):
        return dict.fromkeys(COUNTS)
    cache_read = (
        0
        if "cache_read_input_tokens" not in raw
        else token(raw["cache_read_input_tokens"])
    )
    cache_create = (
        0
        if "cache_creation_input_tokens" not in raw
        else token(raw["cache_creation_input_tokens"])
    )
    base = token(raw["input_tokens"]) if "input_tokens" in raw else None
    if base is None or cache_read is None or cache_create is None:
        combined: int | None = None
    else:
        combined = base + cache_read + cache_create
    return {
        "input_tokens": combined,
        "cached_tokens": cache_read,
        "output_tokens": token(raw["output_tokens"])
        if "output_tokens" in raw
        else None,
        "reasoning_tokens": (
            token(raw["reasoning_tokens"]) if "reasoning_tokens" in raw else None
        ),
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
    source = meta.get("provenance")
    if grok:
        parsed = source == GROK_PROVENANCE
        provenance = GROK_PROVENANCE if parsed else "unsupported"
    else:
        parsed = source == CODEX_PROVENANCE
        if isinstance(source, str):
            provenance = str(source)
        else:
            provenance = "none"
    tokens = {name: token(meta.get(name)) if parsed else None for name in COUNTS}
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


def import_claude(
    path: Path, transcript: Path, phase: str, item: str | None, agent: str | None
) -> None:
    events: list[dict[str, Any]] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    uuids = [event["uuid"] for event in events if isinstance(event.get("uuid"), str)]
    if not uuids:
        print("No new messages.")
        return
    with _ledger_file(path) as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        cursor = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("transcript") == str(transcript):
                stored_cursor = row.get("cursor")
                cursor = stored_cursor if isinstance(stored_cursor, str) else None
        if cursor is not None and cursor not in uuids:
            print("cursor not found; importing from the start", file=sys.stderr)
            cursor = None
        active = cursor is None
        seen: set[str] = set()
        totals: dict[str, int | None] | None = None
        model = None
        for event in events:
            if not active:
                event_uuid = event.get("uuid")
                active = isinstance(event_uuid, str) and event_uuid == cursor
                continue
            message = event.get("message")
            if event.get("type") != "assistant" or not isinstance(message, dict):
                continue
            raw = message.get("usage")
            ident = message.get("id")
            if not isinstance(raw, dict) or not isinstance(ident, str) or ident in seen:
                continue
            seen.add(ident)
            details = raw.get("output_tokens_details", {})
            usage = {
                **dict.fromkeys(
                    ("cache_read_input_tokens", "cache_creation_input_tokens")
                ),
                **raw,
                "reasoning_tokens": details.get("thinking_tokens", 0)
                if isinstance(details, dict)
                else None,
            }
            counts = parse_grok_usage({"type": "end", "usage": usage})
            assert counts is not None
            totals = add_counts(totals, counts)
            model = message.get("model")
        if totals is None:
            print("No new messages.")
            return
        row = {
            "id": str(uuid4()),
            "work_item": item,
            "phase": phase,
            "provider": "claude",
            "model": model,
            "effort": None,
            "outcome": "completed",
            "elapsed_ms": 0,
            **totals,
            "provenance": "claude.transcript",
            "coverage": coverage(totals, "claude.transcript"),
            "transcript": str(transcript),
            "cursor": uuids[-1],
            "messages": len(seen),
            "agent_type": agent,
        }
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(
        f"imported {phase} messages={len(seen)} "
        f"input={totals['input_tokens']} output={totals['output_tokens']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-item")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--claude-transcript", type=Path)
    modes.add_argument("--set-work-item")
    modes.add_argument("--clear-work-item", action="store_true")
    parser.add_argument("--phase", choices=("coordinate", "junior"))
    parser.add_argument("--agent-type")
    args = parser.parse_args()
    if args.claude_transcript is not None and args.phase is None:
        parser.error("--phase MUST accompany --claude-transcript")
    if args.claude_transcript is None and (args.phase or args.agent_type):
        parser.error("--phase and --agent-type MUST accompany --claude-transcript")
    if (args.set_work_item is not None or args.clear_work_item) and args.work_item:
        parser.error("Work item modes MUST NOT use --work-item")
    item: str | None = None
    if args.work_item is not None:
        try:
            item = work_item_id(args.work_item)
        except ValueError as error:
            parser.error(str(error))
    path = ledger_path(args.cwd.resolve())
    marker = path.parent / ".fewia-supervisor-work-item"
    try:
        if args.set_work_item is not None:
            marker.write_text(work_item_id(args.set_work_item) + "\n", encoding="utf-8")
            return
        if args.clear_work_item:
            marker.unlink(missing_ok=True)
            return
        if args.claude_transcript is not None:
            if item is None and marker.is_file():
                stored = marker.read_text(encoding="utf-8").strip()
                item = work_item_id(stored) if stored else None
            import_claude(
                path,
                args.claude_transcript.resolve(),
                args.phase,
                item,
                args.agent_type,
            )
            return
    except ValueError as error:
        parser.error(str(error))
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
