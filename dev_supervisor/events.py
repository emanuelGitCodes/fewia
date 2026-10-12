from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from dev_supervisor.usage import (
    CLAUDE_PROVENANCE,
    CODEX_PROVENANCE,
    GROK_PROVENANCE,
    add_counts,
    parse_claude_usage,
    parse_codex_usage,
    parse_grok_usage,
)

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
CLAUDE_CODES = {
    "rate_limit": "rate_limit",
    "overloaded": "unavailable",
    "server_error": "unavailable",
    "model_not_found": "unavailable",
    "authentication_failed": "unavailable",
    "oauth_org_not_allowed": "unavailable",
    "billing_error": "quota",
    "account_on_hold": "quota",
}


def _content(event: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == kind
    ]


@dataclass
class Events:
    failure: str = "unknown"
    active_tools: set[str] = field(default_factory=set)
    questions: set[str] = field(default_factory=set)
    hold: bool = False
    waiting: bool = False
    complete: bool = False
    saw_error: bool = False
    tokens: dict[str, int | None] | None = None
    provenance: str = "none"

    def feed(self, line: str) -> None:
        try:
            event: Any = json.loads(line)
        except (ValueError, TypeError):
            return
        if not isinstance(event, dict):
            return
        parsed = parse_codex_usage(cast(dict[str, Any], event))
        if parsed is not None:
            self.tokens = add_counts(self.tokens, parsed)
            self.provenance = CODEX_PROVENANCE
        grok = parse_grok_usage(cast(dict[str, Any], event))
        if grok is not None:
            self.tokens = add_counts(self.tokens, grok)
            self.provenance = GROK_PROVENANCE
        claude = parse_claude_usage(cast(dict[str, Any], event))
        if claude is not None:
            self.tokens = add_counts(self.tokens, claude)
            self.provenance = CLAUDE_PROVENANCE
        kind = event.get("type")
        if kind == "result":
            if event.get("subtype") == "success" and event.get("is_error") is False:
                self.complete = True
                self.failure, self.saw_error = "unknown", False
            else:
                self.saw_error = True
        elif kind == "system" and event.get("subtype") == "api_retry":
            self.saw_error = True
            self.failure = CLAUDE_CODES.get(str(event.get("error")), "unknown")
        elif kind == "assistant":
            for block in _content(event, "tool_use"):
                self.active_tools.add(str(block.get("id", "unknown")))
        elif kind == "user":
            for block in _content(event, "tool_result"):
                self.active_tools.discard(str(block.get("tool_use_id", "unknown")))
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
        if kind == "turn.completed" or (
            kind == "end" and event.get("stopReason") == "end_turn"
        ):
            self.complete = True
            self.failure, self.saw_error = "unknown", False
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
