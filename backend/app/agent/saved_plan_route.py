import re
from typing import Literal

from app.agent.chat_answer import _usd
from app.agent.plan_tools import GET_PLAN_TOOL
from app.agent.read_answers import read_tool_answer
from app.domain.budget import STALE_SPENDING_WARNING

_SUBJECT = r"(?:my|the|this|our)(?: saved| current| whole)? plan"
_WHEN = r"(?: right now| now| today)?"
_LIMIT = r"(?:my |the )?(?:monthly )?(?:budget|allowance|cap)"
_COST = re.compile(
    rf"(?:(?:what(?:'s| is| does)|remind me what|tell me what) {_SUBJECT} "
    rf"(?:costs?|total){_WHEN}"
    rf"|how much (?:is|does) {_SUBJECT}(?: cost)?{_WHEN})"
)
_FIT = re.compile(
    rf"(?:(?:does|will|can) {_SUBJECT} fit (?:in |within )?{_LIMIT}"
    rf"|is {_SUBJECT} (?:within|under|over|below|above) {_LIMIT}"
    rf"|can i afford {_SUBJECT}"
    rf"|is {_SUBJECT} affordable)"
)


def saved_plan_read(message: str) -> Literal["cost", "fit"] | None:
    """Classify a narrow question about the saved plan's cost or budget fit."""
    text = " ".join(message.casefold().split())
    if text[-1:] in ("?", ".", "!"):
        text = text[:-1].strip()
    if _FIT.fullmatch(text):
        return "fit"
    if _COST.fullmatch(text):
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
        if not isinstance(display, dict):
            display = {}
        estimate = plan.get("estimate")
        total = estimate.get("total_cents") if isinstance(estimate, dict) else None
        available: object = display.get("available")
        if isinstance(estimate, dict):
            cents = estimate.get("available_cents")
            if type(cents) is int:
                available = _usd(cents)
        if type(total) is not int and isinstance(available, str):
            text = f"{text} Available: {available}."
        pending = display.get("pending")
        if isinstance(pending, str):
            text = f"{text} Pending: {pending}."
    if stale and STALE_SPENDING_WARNING not in text:
        text = f"{text} {STALE_SPENDING_WARNING}"
    return text
