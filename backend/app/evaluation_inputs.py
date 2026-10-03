import re
from dataclasses import dataclass
from datetime import date
from typing import cast

from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN
from app.domain.budget import BudgetResult, StaleSpendingError
from app.evaluation_budget_inputs import fixture_budget

INVALID_INPUT_ERROR = "evaluation inputs are invalid"
STALE_INPUT_ERROR = "evaluation spending is stale without a cap"
CREDENTIAL_INPUT_ERROR = "evaluation inputs contain credential-like text"
CREDENTIAL_PATTERN: re.Pattern[str] = re.compile(
    r"\d{9,}|\b(?:password|passcode|routing|account number|ssn|pin|login)\b",
    re.IGNORECASE,
)
MAX_CASE_MESSAGES = MAX_HISTORY // 2 + 1
_BUDGET_KEYS = (
    "now",
    "budget_period",
    "spending_period",
    "monthly_limit_cents",
    "posted_cents",
    "pending_cents",
    "plan_cap_cents",
    "spending_refreshed_at",
    "user_id",
)
_TEXT_KEYS = ("diet", "followup_diet", "requested_recipe_id", "hostile_url")
_LIST_KEYS = ("pantry_ingredients", "ingredient_exclusions", "unknown_restrictions")
_LIMIT_KEYS = ("max_model_turns", "max_planner_revisions")


class EvaluationInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CaseContext:
    case_id: str
    messages: tuple[str, ...]
    inputs: dict[str, object]
    period: date
    budget: BudgetResult
    plan_cap_cents: int | None
    user_id: int


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_MESSAGE_LEN:
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    return value


def _copy_inputs(source: dict[str, object]) -> dict[str, object]:
    inputs = {key: source[key] for key in _BUDGET_KEYS if key in source}
    if any(type(value) not in (str, int, type(None)) for value in inputs.values()):
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    for key in _TEXT_KEYS:
        if key in source:
            inputs[key] = _text(source[key])
    for key in _LIST_KEYS:
        if key in source:
            value = source[key]
            if type(value) is not list:
                raise EvaluationInputError(INVALID_INPUT_ERROR)
            inputs[key] = [_text(item) for item in value]
    for key in ("meals", "followup_meals"):
        if key not in source:
            continue
        value = source[key]
        if type(value) is not list or len(value) > 3:
            raise EvaluationInputError(INVALID_INPUT_ERROR)
        meals: list[dict[str, object]] = []
        for item in value:
            if type(item) is not dict:
                raise EvaluationInputError(INVALID_INPUT_ERROR)
            servings = item.get("servings")
            if type(servings) is not int or not 1 <= servings <= 8:
                raise EvaluationInputError(INVALID_INPUT_ERROR)
            meals.append(
                {"recipe_id": _text(item.get("recipe_id")), "servings": servings}
            )
        inputs[key] = meals
    for key in _LIMIT_KEYS:
        if key in source:
            value = source[key]
            if type(value) is not int or value < 1:
                raise EvaluationInputError(INVALID_INPUT_ERROR)
            inputs[key] = value
    return inputs


def prepare_case(case: dict[str, object]) -> CaseContext:
    if type(case) is not dict:
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    case_id = _text(case.get("id"))
    raw_messages = case.get("messages")
    if (
        type(raw_messages) is not list
        or not 1 <= len(raw_messages) <= MAX_CASE_MESSAGES
    ):
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    messages: list[str] = []
    for item in raw_messages:
        if type(item) is not dict or item.get("role") != "user":
            raise EvaluationInputError(INVALID_INPUT_ERROR)
        content = _text(item.get("content"))
        if CREDENTIAL_PATTERN.search(content):
            raise EvaluationInputError(CREDENTIAL_INPUT_ERROR)
        messages.append(content)
    source = case.get("inputs")
    if type(source) is not dict:
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    inputs = _copy_inputs(cast(dict[str, object], source))
    user_id = inputs.get("user_id")
    cap = inputs.get("plan_cap_cents")
    if type(user_id) is not int or user_id < 1:
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    if cap is not None and (type(cap) is not int or cap < 0):
        raise EvaluationInputError(INVALID_INPUT_ERROR)
    try:
        period = date.fromisoformat(_text(inputs.get("budget_period")))
        if period.day != 1:
            raise EvaluationInputError(INVALID_INPUT_ERROR)
        if "spending_period" in inputs:
            spending_period = date.fromisoformat(_text(inputs["spending_period"]))
            if spending_period != period:
                raise EvaluationInputError(INVALID_INPUT_ERROR)
        budget = fixture_budget(inputs)
    except StaleSpendingError:
        raise EvaluationInputError(STALE_INPUT_ERROR) from None
    except (TypeError, ValueError, OverflowError):
        raise EvaluationInputError(INVALID_INPUT_ERROR) from None
    return CaseContext(case_id, tuple(messages), inputs, period, budget, cap, user_id)
