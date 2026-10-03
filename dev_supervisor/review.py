from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from pathlib import Path
from typing import IO, Any, cast

from dev_supervisor.process import stop
from dev_supervisor.usage import (
    CODEX_PROVENANCE,
    GROK_PROVENANCE,
    add_counts,
    ledger_path,
    parse_codex_usage,
    parse_grok_usage,
    write_usage,
)

REVIEW_DEFAULT = {"grok-4.6": "gpt-6-luna", "gpt-5.3-codex-spark": "gpt-6-luna"}
REVIEW_DEFAULT["gpt-6-luna"] = "gpt-6.1-sol"
REVIEW_DEFAULT["gpt-6.1-sol"] = "gpt-6-luna"
GROK_MODEL = "grok-4.6"
DIFF_LIMIT = 3000
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
NO_SHELL = "Do not run shell commands; the diff is below"
VERDICT_PAT = re.compile(
    r"[*_`~]*VERDICT[*_`~]*\s*:\s*[*_`~]*(APPROVE|REQUEST_CHANGES|BLOCKED)[*_`~]*"
)


def parse_verdict(text: str) -> tuple[str, bool]:
    hits = VERDICT_PAT.findall(text)
    return (hits[-1], True) if hits else ("BLOCKED", False)


def grok_effort(complexity: str) -> str:
    if complexity == "simple":
        return "low"
    return "medium"


def choose_provider(requested: str) -> str:
    if requested != "auto":
        return requested
    if "CODEX_SANDBOX" in os.environ:
        return "grok"
    return "codex"


def truncate_diff(text: str, limit: int = DIFF_LIMIT) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    note = f"truncated: showing {limit} of {len(lines)} lines"
    return "\n".join(lines[:limit]) + "\n" + note + "\n"


def first_error(raw: bytes) -> str:
    plain = ""
    for line in raw.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if line.strip() and not plain:
                plain = line.strip()[:200]
            continue
        if isinstance(event, dict) and event.get("type") in ("error", "turn.failed"):
            msg = event.get("message")
            if isinstance(msg, str) and msg:
                return msg[:200]
            nested = event.get("error")
            if isinstance(nested, dict):
                nested_msg = nested.get("message")
                if isinstance(nested_msg, str) and nested_msg:
                    return nested_msg[:200]
    return plain


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


def fallback_reason(raw: bytes) -> str | None:
    reasons = {
        "unavailable": (
            "provider_unavailable",
            "service_unavailable",
            "model_not_found",
            "HTTP 503 service unavailable",
        ),
        "authentication": (
            "authentication_error",
            "unauthorized",
            "HTTP 401 unauthorized",
        ),
        "quota": (
            "insufficient_quota",
            "quota_exceeded",
            "usage_limit_reached",
            "HTTP 429 quota exceeded",
        ),
        "rate_limit": (
            "rate_limit_exceeded",
            "rate_limit_error",
            "HTTP 429 rate limit exceeded",
        ),
    }
    reason = None
    for line in raw.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            return None
        if event.get("type") not in ("error", "turn.failed"):
            continue
        error = event.get("error", event)
        if not isinstance(error, dict):
            return None
        value = error.get("code", error.get("message"))
        matches = [key for key, values in reasons.items() if value in values]
        if not matches or (reason is not None and reason != "codex_" + matches[0]):
            return None
        reason = "codex_" + matches[0]
    return reason


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


def git_text(cwd: Path, *flags: str) -> str:
    return subprocess.check_output(["git", *flags], cwd=cwd, text=True)


def run_grok(args: list[str], cwd: Path, timeout: float) -> tuple[bytes, bool, int]:
    with Path(os.devnull).open("rb") as source:
        return run_codex(args, cwd, source, timeout)


def grok_report(raw: bytes) -> tuple[str, dict[str, int | None] | None]:
    chunks: list[str] = []
    totals: dict[str, int | None] | None = None
    for line in raw.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        payload = cast(dict[str, Any], event)
        if payload.get("type") == "text":
            data = payload.get("data")
            if isinstance(data, str):
                chunks.append(data)
            continue
        usage = parse_grok_usage(payload)
        if usage is not None:
            totals = usage
    return "".join(chunks), totals


def grok_command(cwd: Path, prompt: Path, effort: str) -> list[str]:
    cmd = [str(Path.home() / ".grok/bin/grok"), "--model", GROK_MODEL]
    cmd += ["--reasoning-effort", effort, "--cwd", str(cwd)]
    cmd += ["--prompt-file", str(prompt), "--output-format", "streaming-json"]
    cmd += ["--max-turns", "20", "--no-subagents"]
    cmd += ["--permission-mode", "default"]
    cmd += ["--tools", "Read,Grep,Glob"]
    cmd += ["--disallowed-tools", "search_tool,use_tool"]
    cmd += ["--disable-web-search"]
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("--cwd", "--base", "--brief", "--writer-model"):
        parser.add_argument(name, required=True)
    parser.add_argument("--complexity", required=True, choices=tuple(EFFORT))
    for opt in ("--model", "--work-item", "--gates-file"):
        parser.add_argument(opt)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--provider", choices=("auto", "codex", "grok"), default="auto")
    args = parser.parse_args()
    cwd = Path(args.cwd).resolve()

    def git(*flags: str) -> str:
        return git_text(cwd, *flags)

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
    provider = choose_provider(args.provider)
    if provider == "grok":
        model = GROK_MODEL
        effort = grok_effort(args.complexity)
    else:
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
    if provider == "grok":
        parts.append(NO_SHELL)
        parts.append(truncate_diff(git("diff", f"{args.base}...{sha}")))
    dest = root / ".fewia-supervisor-reviews" / f"{sha}-{model}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    attempted_providers = [provider]
    fallback: str | None = None
    codex_attempt: dict[str, object] | None = None
    allow_fallback = (
        args.provider == "auto"
        and args.model is None
        and args.writer_model != GROK_MODEL
    )
    if provider == "codex":
        cmd = ["codex", "exec", "--model", model, "--cd", str(cwd)]
        cmd += [
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--json",
        ]
        cmd += ["-c", f'model_reasoning_effort="{effort}"', "-o", str(dest), "-"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text("\n".join(parts))
            with prompt_path.open("rb") as source:
                try:
                    raw, timed_out, elapsed_ms = run_codex(
                        cmd, cwd, source, args.timeout
                    )
                except FileNotFoundError as exc:
                    if not allow_fallback or exc.filename not in (None, cmd[0]):
                        raise
                    raw, timed_out, elapsed_ms = b"", False, 0
                    fallback = "codex_executable_missing"
        totals = parse_stdout(raw)
        if (
            allow_fallback
            and not timed_out
            and (not dest.exists() or not dest.read_text().strip())
        ):
            fallback = fallback or fallback_reason(raw)
        else:
            fallback = None
        if fallback is not None:
            codex_attempt = dict(
                provider=provider,
                model=model,
                effort=effort,
                elapsed_ms=elapsed_ms,
                outcome="task_failed",
                usage=totals,
                fallback_reason=fallback,
            )
            provider, model, effort = "grok", GROK_MODEL, grok_effort(args.complexity)
            attempted_providers.append(provider)
            parts += [NO_SHELL, truncate_diff(git("diff", f"{args.base}...{sha}"))]
            dest = dest.with_name(f"{sha}-{model}.md")
            dest.unlink(missing_ok=True)
    if provider == "grok":
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text("\n".join(parts))
            grok_cmd = grok_command(cwd, prompt_path, effort)
            raw, timed_out, elapsed_ms = run_grok(grok_cmd, cwd, args.timeout)
        text, totals = grok_report(raw)
        if text.strip():
            dest.write_text(text)
    if not dest.exists() or dest.stat().st_size == 0:
        reason = "timed out" if timed_out else "produced no output"
        err = first_error(raw)
        extra_err = f" {err}" if err else ""
        dest.write_text(f"No review report. {provider} {reason}.{extra_err}\n")
    message = dest.read_text()
    verdict, found = parse_verdict(message)
    outcome = "timeout" if timed_out else "completed" if found else "task_failed"
    lines = message.splitlines()
    extra = f"\n... truncated, full text: {dest}" if len(lines) > 60 else ""
    print("\n".join(lines[:60]) + extra)
    inn = None if totals is None else totals["input_tokens"]
    body: dict[str, object] = dict(verdict=verdict, model=model, effort=effort, sha=sha)
    body.update(elapsed_ms=elapsed_ms, saved=str(dest), input_tokens=inn)
    body["output_tokens"] = None if totals is None else totals["output_tokens"]
    body["provider"] = provider
    body.update(attempted_providers=attempted_providers, fallback_reason=fallback)
    if codex_attempt is not None:
        body["codex_attempt"] = codex_attempt
    print(json.dumps(body))
    meta: dict[str, Any] = {"provenance": "none"}
    if totals is not None:
        provenance = GROK_PROVENANCE if provider == "grok" else CODEX_PROVENANCE
        meta = {"provenance": provenance, **totals}
    rec = [ledger_path(cwd), str(uuid.uuid4()), args.work_item, "review", provider]
    write_usage(*cast(Any, rec + [model, effort, outcome, meta, elapsed_ms]))
    raise SystemExit({"APPROVE": 0, "REQUEST_CHANGES": 1}.get(verdict, 2))


if __name__ == "__main__":
    main()
