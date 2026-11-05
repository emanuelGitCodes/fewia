import re
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from json import dumps
from typing import TypeGuard, cast, get_args

from pydantic import ValidationError

from app.agent.catalog_tool import (
    CatalogToolError,
    execute_catalog_search,
    page_arguments,
)
from app.agent.chat_messages import ChatProtocolError
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest
from app.domain.meal_tags import SEARCH_TERMS, TAG_ORDER, resolve_meal_term

MAX_MESSAGE_LEN = 4000
MAX_HISTORY = 8
_ROLES = ("user", "assistant")
_REQUEST = "request is invalid"
_PREVIOUS = "previous_request is invalid"
_CONTEXT_ROLE = (
    "previous_request is prior state; apply latest explicit additions and removals"
    "; plan_meals is the user's current plan"
    "; previous_search holds the search_meals arguments for the next page of the "
    "last search; use them unchanged only for an explicit more request with "
    "no new restrictions"
)
_PREVIOUS_SEARCH = "previous_search is invalid"
MAX_PLAN_MEALS = 3
_CONTINUATION = re.compile(
    r"(?:please )?(?:(?:show|give)(?: me)? )?"
    r"(?:more(?: (?:meals|ideas|options|choices))?|"
    r"(?:the )?next(?: page| meals| ideas| options| choices)?)"
    r"(?:,? please)?"
)
_MODIFIED_CONTINUATION = re.compile(
    rf"{_CONTINUATION.pattern}(?:,\s*|\s+)(?:but|only|instead|without|exclude)\b"
)
_NEW_SEARCH_REQUEST = re.compile(
    r"(?:please,? )?(?:(?:find|show|give)(?: me)? )?"
    r"([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?)"
    r"(?: (?:meals|ideas|options|recipes))?"
    r"(?:[,!.?]? please)?[,!.?]*"
)
_MORE_TYPE_REQUEST = re.compile(
    r"(?:please,? )?(?:(?:show|give)(?: me)? )?"
    r"(?:more ([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?)"
    r"|the ([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?) ones)"
    r"(?: (?:meals|ideas|options|recipes))?"
    r"(?:[,!.?]? please)?[,!.?]*"
)
_RESTART_ACTION = (
    r"(?:(?:start (?:over|again)|restart(?: (?:the )?search)?)"
    r"(?: (?:from|at) (?:the )?(?:first page|beginning))?"
    r"|start (?:from|at) (?:the )?first page)"
)
_RESTART_REQUEST = re.compile(
    r"(?:please,? )?(?:"
    rf"{_RESTART_ACTION}|"
    r"(?:(?:show|give)(?: me)? )?(?:the )?first page(?: again)?|"
    r"(?:go (?:back )?to|back to) (?:the )?first page)"
    r"(?:[,!.?]? please)?[,!.?]*"
)
_RESTART_TYPE_REQUEST = re.compile(
    r"(?:please,? )?(?:"
    rf"{_RESTART_ACTION} (?:with|for) "
    r"([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?)"
    r"(?: (?:meals|ideas|options|recipes))?|"
    r"(?:show|give)(?: me)? (?:the )?first page of "
    r"([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?)"
    r"(?: (?:meals|ideas|options|recipes))?(?: again)?|"
    r"(?:find|show|give)(?: me)? "
    r"([a-z][a-z_-]*(?: [a-z][a-z_-]*)*?)"
    r"(?: (?:meals|ideas|options|recipes))?"
    r" (?:again|(?:from|at) (?:the )?first page))"
    r"(?:[,!.?]? please)?[,!.?]*"
)
_MAX_MEAL_TERM_WORDS = max(
    len(term.replace("_", " ").replace("-", " ").split())
    for term in (*SEARCH_TERMS, *TAG_ORDER)
)


def _search_text(message: str) -> str:
    text = message.strip()
    if text.startswith("My current plan: "):
        prefix, separator, text = text.partition("\n\n")
        if not separator or ". Pantry: " not in prefix or ". Plan cap: " not in prefix:
            return ""
    return " ".join(text.casefold().strip(" .!?").split())


def is_search_continuation(message: str) -> bool:
    return _CONTINUATION.fullmatch(_search_text(message)) is not None


def is_modified_search_continuation(message: str) -> bool:
    return _MODIFIED_CONTINUATION.match(_search_text(message)) is not None


def _meal_terms(text: str) -> bool:
    words = text.split()
    while words:
        for size in range(min(len(words), _MAX_MEAL_TERM_WORDS), 0, -1):
            if resolve_meal_term(" ".join(words[:size])) is not None:
                words = words[size:]
                break
        else:
            return False
    return True


def more_type_query(message: str) -> str | None:
    request = _MORE_TYPE_REQUEST.fullmatch(_search_text(message))
    terms = None if request is None else request.group(1) or request.group(2)
    return terms if terms and _meal_terms(terms) else None


def restart_type_query(message: str) -> str | None:
    request = _RESTART_TYPE_REQUEST.fullmatch(_search_text(message))
    if request is None:
        return None
    terms = next(term for term in request.groups() if term is not None)
    if _meal_terms(terms):
        return terms
    try:
        found = execute_catalog_search({"query": terms})
    except CatalogToolError:
        return None
    return (
        terms
        if found["status"] == "ok"
        and not any(found[key] for key in ("unmatched", "unsupported", "dropped"))
        else None
    )


def is_search_restart(message: str) -> bool:
    return (
        _RESTART_REQUEST.fullmatch(_search_text(message)) is not None
        or restart_type_query(message) is not None
    )


def is_new_search_request(message: str) -> bool:
    request = _NEW_SEARCH_REQUEST.fullmatch(_search_text(message))
    if request is not None and _meal_terms(request.group(1)):
        return True
    return (
        more_type_query(message) is not None or restart_type_query(message) is not None
    )


def validated_previous_search(
    value: dict[str, object] | None,
) -> dict[str, object] | None:
    search = None if value is None else page_arguments(value)
    if value is not None and search is None:
        raise ChatProtocolError(_PREVIOUS_SEARCH)
    return deepcopy(search)


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
    previous_search: dict[str, object] | None = None,
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
    search = validated_previous_search(previous_search)
    messages = _history(history)
    context = dumps(
        {
            "budget": asdict(budget),
            "context_role": _CONTEXT_ROLE,
            "period": period.isoformat(),
            "plan_cap_cents": plan_cap_cents,
            "plan_meals": meals,
            "previous_request": previous,
            "previous_search": search,
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
