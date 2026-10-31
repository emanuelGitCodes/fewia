from dataclasses import asdict
from datetime import date
from json import dumps
from typing import TypeGuard, cast, get_args

from pydantic import ValidationError

from app.agent.chat_messages import ChatProtocolError
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest

MAX_MESSAGE_LEN = 4000
MAX_HISTORY = 8
_ROLES = ("user", "assistant")
_REQUEST = "request is invalid"
_PREVIOUS = "previous_request is invalid"
_CONTEXT_ROLE = (
    "previous_request is prior state; apply latest explicit additions and removals"
    "; plan_meals is the user's current plan"
)
MAX_PLAN_MEALS = 3


def plan_ingredient_ids(plan: object) -> list[str] | None:
    if not isinstance(plan, dict) or not isinstance(plan.get("lines"), list):
        return None
    ids: set[str] = set()
    for line in plan["lines"]:
        ingredient_id = line.get("ingredient_id") if isinstance(line, dict) else None
        if isinstance(ingredient_id, str) and ingredient_id in INGREDIENTS:
            ids.add(ingredient_id)
    return sorted(ids)


def _exact_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _plan_cap_ok(value: object) -> TypeGuard[int | None]:
    return value is None or (_exact_int(value) and value >= 0)


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


def _plan_meals(
    plan_meals: list[dict[str, object]] | None,
) -> list[dict[str, object]] | None:
    if plan_meals is None:
        return None
    if not isinstance(plan_meals, list) or len(plan_meals) > MAX_PLAN_MEALS:
        raise ChatProtocolError(_REQUEST)
    meals: list[dict[str, object]] = []
    for meal in plan_meals:
        recipe_id = meal.get("recipe_id") if isinstance(meal, dict) else None
        servings = meal.get("servings") if isinstance(meal, dict) else None
        if (
            not isinstance(recipe_id, str)
            or recipe_id not in SUPPORTED_RECIPE_IDS
            or not _exact_int(servings)
            or not 1 <= servings <= 8
        ):
            raise ChatProtocolError(_REQUEST)
        meals.append({"recipe_id": recipe_id, "servings": servings})
    return meals


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
    spending_source: SpendingSource = "fixture",
    previous_request: dict[str, object] | None = None,
    previous_ingredient_ids: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    plan_cap_cents: int | None = None,
    plan_meals: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if (
        not _public_text(message)
        or not _exact_int(user_id)
        or user_id < 1
        or spending_source not in get_args(SpendingSource)
        or type(period) is not date
        or period.day != 1
        or not _budget_ok(budget)
        or not _plan_cap_ok(plan_cap_cents)
    ):
        raise ChatProtocolError(_REQUEST)
    previous = _previous(previous_request)
    if previous_ingredient_ids is not None and (
        not isinstance(previous_ingredient_ids, list)
        or len(previous_ingredient_ids) > len(INGREDIENTS)
        or any(
            not isinstance(item, str) or item not in INGREDIENTS
            for item in previous_ingredient_ids
        )
    ):
        raise ChatProtocolError(_PREVIOUS)
    meals = _plan_meals(plan_meals)
    messages = _history(history)
    context = dumps(
        {
            "budget": asdict(budget),
            "context_role": _CONTEXT_ROLE,
            "period": period.isoformat(),
            "plan_cap_cents": plan_cap_cents,
            "plan_meals": meals,
            "previous_request": previous,
            "previous_ingredient_ids": (
                None
                if previous_ingredient_ids is None
                else sorted(previous_ingredient_ids)
            ),
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
    result = {"inputTokens": input_tokens, "outputTokens": output_tokens}
    for key in ("cacheReadInputTokens", "cacheWriteInputTokens"):
        value = usage.get(key)
        if _exact_int(value) and value >= 0:
            result[key] = value
    return result


def sum_usage(
    total: dict[str, int] | None, response: object, *, first: bool
) -> dict[str, int] | None:
    part = read_usage(response)
    if total is None or part is None:
        return None
    result = {
        "inputTokens": total["inputTokens"] + part["inputTokens"],
        "outputTokens": total["outputTokens"] + part["outputTokens"],
    }
    for key in ("cacheReadInputTokens", "cacheWriteInputTokens"):
        if key in part and (first or key in total):
            result[key] = total.get(key, 0) + part[key]
    return result
