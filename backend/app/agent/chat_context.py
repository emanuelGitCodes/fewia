from dataclasses import asdict
from datetime import date
from json import dumps
from typing import Literal, TypeGuard, cast

from pydantic import ValidationError

from app.agent.chat_messages import ChatProtocolError
from app.domain.budget import BudgetResult
from app.domain.grocery import GroceryRequest

MAX_MESSAGE_LEN = 4000
MAX_HISTORY = 8
_SOURCES = frozenset({"fixture", "plaid_sandbox"})
_ROLES = ("user", "assistant")
_REQUEST = "request is invalid"
_PREVIOUS = "previous_request is invalid"
CONTEXT_ROLE = (
    "previous_request is prior state; apply latest explicit additions and removals"
)


def _exact_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _public_text(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_MESSAGE_LEN
    )


def _budget_ok(budget: object) -> TypeGuard[BudgetResult]:
    if not isinstance(budget, BudgetResult):
        return False
    return (
        _exact_int(budget.available_cents)
        and budget.available_cents >= 0
        and _exact_int(budget.pending_cents)
        and type(budget.stale) is bool
        and type(budget.warnings) is tuple
        and all(type(item) is str for item in budget.warnings)
    )


def _previous(
    previous_request: dict[str, object] | None,
) -> dict[str, object] | None:
    if previous_request is None:
        return None
    dumped: object = None
    if isinstance(previous_request, dict):
        try:
            dumped = GroceryRequest.model_validate(previous_request).model_dump(
                mode="json"
            )
        except ValidationError:
            dumped = None
    if isinstance(dumped, dict):
        return cast(dict[str, object], dumped)
    raise ChatProtocolError(_PREVIOUS)


def _history(history: list[dict[str, str]] | None) -> list[dict[str, object]]:
    if history is None:
        return []
    if not isinstance(history, list) or len(history) > MAX_HISTORY or len(history) % 2:
        raise ChatProtocolError(_REQUEST)
    messages: list[dict[str, object]] = []
    for index, item in enumerate(history):
        role = _ROLES[index % 2]
        text = None if not isinstance(item, dict) else item.get("text")
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "text"}
            or item.get("role") != role
            or not _public_text(text)
        ):
            raise ChatProtocolError(_REQUEST)
        messages.append({"role": role, "content": [{"text": text}]})
    return messages


def build_messages(
    message: str,
    budget: BudgetResult,
    period: date,
    *,
    user_id: int = 1,
    spending_source: Literal["fixture", "plaid_sandbox"] = "fixture",
    previous_request: dict[str, object] | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    if (
        not _public_text(message)
        or not _exact_int(user_id)
        or user_id < 1
        or spending_source not in _SOURCES
        or type(period) is not date
        or period.day != 1
        or not _budget_ok(budget)
    ):
        raise ChatProtocolError(_REQUEST)
    previous = _previous(previous_request)
    messages = _history(history)
    context = dumps(
        {
            "budget": asdict(budget),
            "context_role": CONTEXT_ROLE,
            "period": period.isoformat(),
            "previous_request": previous,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    messages.append({"role": "user", "content": [{"text": context}, {"text": message}]})
    return messages


def read_usage(response: object) -> dict[str, int] | None:
    if not isinstance(response, dict):
        return None
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("inputTokens")
    output_tokens = usage.get("outputTokens")
    if (
        not _exact_int(input_tokens)
        or input_tokens < 0
        or not _exact_int(output_tokens)
        or output_tokens < 0
    ):
        return None
    return {"inputTokens": input_tokens, "outputTokens": output_tokens}
