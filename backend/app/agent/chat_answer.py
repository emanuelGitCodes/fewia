from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.services.grocery_planner import safe_conflict

FALLBACK_ANSWER = "The estimate is unavailable."


def _recipe_display_name(recipe_id: str) -> str:
    return recipe_id.replace("_", " ")


_SUPPORTED_RECIPE_NAMES = ", ".join(
    _recipe_display_name(rid) for rid in SUPPORTED_RECIPE_IDS
)
CLARIFY_ANSWER = (
    "Choose a supported recipe and specify pantry or exclusion ingredients "
    "from the sample catalog. Supported recipes: "
    f"{_SUPPORTED_RECIPE_NAMES}. "
    f"Catalog ingredients: {', '.join(item.name for item in INGREDIENTS.values())}."
)
INCOMPLETE_ANSWER = (
    f"The sample estimate is incomplete and is not accepted. {SAMPLE_ESTIMATE_NOTICE}"
)


def format_usd_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def safe_tool_error(block: object) -> dict[str, str] | None:
    if not isinstance(block, dict):
        return None
    result = block.get("toolResult")
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict):
        return None
    body = first.get("json")
    if not isinstance(body, dict):
        return None
    return safe_conflict(body.get("error"), body.get("ingredient_id"))


def _stale_suffix(budget: dict[str, object]) -> str:
    if budget.get("stale") is not True:
        return ""
    return f" {STALE_SPENDING_WARNING}"


def _conflict_answer(error: object) -> str | None:
    if not isinstance(error, dict):
        return None
    conflict = safe_conflict(error.get("error"), error.get("ingredient_id"))
    if conflict is None:
        return None
    ingredient = INGREDIENTS[conflict["ingredient_id"]]
    return (
        f"The recipe includes {ingredient.name}. "
        "Fixed recipes cannot omit it. "
        "Choose another recipe or change the restriction."
    )


def _plan_answer(candidate: dict[str, object]) -> str | None:
    plan = candidate.get("plan")
    budget = candidate.get("budget")
    if not isinstance(plan, dict) or not isinstance(budget, dict):
        return None
    total = plan.get("total_cents")
    available = budget.get("available_cents")
    accepted = plan.get("accepted")
    if total is None:
        return f"{INCOMPLETE_ANSWER}{_stale_suffix(budget)}"
    if (
        type(total) is not int
        or type(available) is not int
        or type(accepted) is not bool
    ):
        return None
    total_text = format_usd_cents(total)
    available_text = format_usd_cents(available)
    if accepted is True:
        text = (
            f"The sample estimate total is {total_text} against a planning "
            f"budget of {available_text}. {SAMPLE_ESTIMATE_NOTICE}"
        )
    else:
        text = (
            f"The sample estimate total is {total_text}. "
            f"The available planning budget is {available_text}. "
            "Revise the request. The estimate is not reduced. "
            f"{SAMPLE_ESTIMATE_NOTICE}"
        )
    return f"{text}{_stale_suffix(budget)}"


def render_public_answer(
    candidate: dict[str, object] | None,
    tool_error: dict[str, str] | None = None,
) -> str:
    """Return a public answer from the plan and allowlisted tool errors."""
    if candidate is not None:
        if not isinstance(candidate, dict):
            return FALLBACK_ANSWER
        planned = _plan_answer(candidate)
        return FALLBACK_ANSWER if planned is None else planned
    conflict = _conflict_answer(tool_error)
    if conflict is not None:
        return conflict
    return CLARIFY_ANSWER
