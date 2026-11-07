import re

from app.agent.read_answers import meal_name
from app.domain.plan_revision import PlanRevisionInput

_ASK = r"(?:(?:please|can you|could you|would you|will you) )?"
_OBJECT = r"(?:it|that|this|that one|this one|that meal|this meal)"
_TARGET = (
    r"(?: (?:to|on|in|into|onto) (?:my |the |our )?"
    r"(?:plan|saved plan|list|meals|meal list|list of meals|shopping list))?"
)
_SAVE = re.compile(rf"{_ASK}(?:add|save|put) {_OBJECT}{_TARGET}(?: please)?")
_LIMIT = (
    "I cannot save an ingredient change to your plan yet. That result was a what-if."
)


def asks_to_save_what_if(message: str) -> bool:
    text = " ".join(message.casefold().split())
    if text[-1:] in ("?", ".", "!"):
        text = text[:-1].strip()
    return _SAVE.fullmatch(text) is not None


def swap_not_saved_reply(recipe_id: str, plan: PlanRevisionInput | None) -> str:
    meal = meal_name(recipe_id)
    if plan is not None and any(m.recipe_id == recipe_id for m in plan.snapshot.meals):
        return f"{_LIMIT} {meal} is already in your plan as listed."
    return f"{_LIMIT} To add the listed meal, say: add {meal} to my plan."
