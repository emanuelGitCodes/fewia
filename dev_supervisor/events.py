from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from dev_supervisor.usage import add_counts, fingerprint, parse_codex_usage

CODES = {
    "rate_limit_exceeded": "rate_limit",
    "rate_limit_error": "rate_limit",
    "insufficient_quota": "quota",
    "quota_exceeded": "quota",
    "usage_limit_reached": "quota",
    "model_not_found": "unavailable",
    "authentication_error": "unavailable",
    "unauthorized": "unavailable",
    "service_unavailable": "unavailable",
    "FS_PERMISSION_DENIED": "permission",
}


@dataclass
class Events:
    failure: str = "unknown"
    active_tools: set[str] = field(default_factory=set)
    questions: set[str] = field(default_factory=set)
    hold: bool = False
    waiting: bool = False
    complete: bool = False
    saw_error: bool = False
    usage: dict[str, int | None] | None = None
    usage_provenance: str = "none"
    usage_seen: set[str] = field(default_factory=set)
    current_turn: str | None = None
    counted_current: bool = False

    def feed(self, line: str) -> None:
        try:
            event: Any = json.loads(line)
        except (ValueError, TypeError):
            return
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind in {"error", "turn.failed"}:
            self.saw_error = True
            error = event.get("error", event)
            if isinstance(error, dict):
                self.failure = CODES.get(str(error.get("code")), "unknown")
                message = str(error.get("message", ""))
                for code, reason in CODES.items():
                    if f'"{code}"' in message:
                        self.failure = reason
            return
        if kind in {"tool_call", "tool_call_update"}:
            identity = str(event.get("toolCallId", "unknown"))
            if event.get("status") in {"completed", "failed"}:
                self.active_tools.discard(identity)
                self.questions.discard(identity)
            else:
                self.active_tools.add(identity)
                if event.get("toolName") == "ask_user_question":
                    self.questions.add(identity)
        if kind == "turn.started":
            ident = fingerprint(event)
            self.current_turn = ident if ident is not None else ""
            self.counted_current = False
        if kind == "turn.completed" or (
            kind == "end" and event.get("stopReason") == "end_turn"
        ):
            self.complete = True
            self.failure, self.saw_error = "unknown", False
            parsed = parse_codex_usage(event)
            if parsed is not None:
                ident = fingerprint(event)
                if ident is not None:
                    duplicate = ident in self.usage_seen
                    same_turn = self.current_turn == ident and self.counted_current
                    if not duplicate and not same_turn:
                        self.usage_seen.add(ident)
                        self.usage = add_counts(self.usage, parsed)
                        self.usage_provenance = "codex.turn.completed"
                        self.counted_current = True
                elif self.current_turn is not None:
                    if not self.counted_current:
                        self.usage = add_counts(self.usage, parsed)
                        self.usage_provenance = "codex.turn.completed"
                        self.counted_current = True
                else:
                    self.usage = add_counts(self.usage, parsed)
                    self.usage_provenance = "codex.turn.completed"
            elif self.usage_provenance == "none":
                self.usage_provenance = "unsupported"
        if kind in {"permission_request", "user_input_required"}:
            self.hold = True
        item = event.get("item", {})
        if isinstance(item, dict) and item.get("type") in {
            "command_execution",
            "mcp_tool_call",
            "web_search",
        }:
            identity = str(item.get("id", "unknown"))
            if kind == "item.started":
                self.active_tools.add(identity)
            elif kind == "item.completed":
                self.active_tools.discard(identity)
        params = event.get("params") or {}
        update = event.get(
            "update", params.get("update", {}) if isinstance(params, dict) else {}
        )
        if isinstance(update, dict):
            identity = str(update.get("toolCallId", "unknown"))
            if update.get("sessionUpdate") in {"tool_call", "tool_call_update"}:
                if update.get("status") in {"completed", "failed"}:
                    self.active_tools.discard(identity)
                else:
                    self.active_tools.add(identity)
        self.waiting = self.hold or bool(self.questions)

    def outcome(self, returncode: int) -> str:
        if self.waiting:
            return "permission"
        if self.failure != "unknown":
            return self.failure
        return (
            "completed"
            if returncode == 0 and self.complete and not self.saw_error
            else "task_failed"
        )
