import re
from typing import Literal

from app.agent.plan_tools import GET_PLAN_TOOL
from app.agent.read_answers import read_tool_answer
from app.domain.budget import STALE_SPENDING_WARNING

_PLAN_SUBJECT = re.compile(
    r"\b(?:my|the|this|our)\s+(?:(?:saved|current|whole)\s+)?plan\b"
)
_OUT_OF_SCOPE = re.compile(
    r"\b(?:add|remove|swap|replace|change|halve|half|double|servings?|with|without|"
    r"if|would|instead|buy|order|checkout|check out|pay|cart|kroger|store|safe|"
    r"meals?|recipes?|ingredients?)(?:s|es|d|ed|ing)?\b"
)
_FIT = re.compile(r"\b(?:fits?|within|afford(?:able)?|budgets?|over|under)\b")
_COST = re.compile(r"\b(?:costs?|total|price)\b")


def saved_plan_read(message: str) -> Literal["cost", "fit"] | None:
    """Classify a narrow question about the saved plan's cost or budget fit."""
    text = " ".join(message.casefold().split())
    if _PLAN_SUBJECT.search(text) is None or _OUT_OF_SCOPE.search(text):
        return None
    if _FIT.search(text):
        return "fit"
    if _COST.search(text):
        return "cost"
    return None


def saved_plan_reply(
    plan: dict[str, object],
    budget_summary: dict[str, object] | None,
    *,
    stale: bool,
) -> str | None:
    """Reuse the get_plan read text; None when the plan cannot be answered."""
    meals = plan.get("meals")
    if not isinstance(meals, list) or not meals:
        return None
    text = read_tool_answer([(GET_PLAN_TOOL, plan)], stale=stale)
    if text is None:
        return None
    if budget_summary is not None:
        display = budget_summary.get("money_display")
        pending = display.get("pending") if isinstance(display, dict) else None
        if isinstance(pending, str):
            text = f"{text} Pending: {pending}."
    if stale and STALE_SPENDING_WARNING not in text:
        text = f"{text} {STALE_SPENDING_WARNING}"
    return text
