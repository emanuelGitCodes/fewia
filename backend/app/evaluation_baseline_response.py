import json
import math
from typing import NoReturn

from app.agent.chat_messages import parse_provider_response
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE

MAX_MESSAGE_LEN = 4000
_MAX_TEXT_LEN = 32768
_RESULT_FIELDS = frozenset({"status", "answer", "request", "plan", "budget"})
_STATUSES = frozenset({"planned", "needs_revision", "clarification"})
_PRIVATE_FIELDS = frozenset(
    {
        "evidence_id",
        "evidence_revision_id",
        "tool_trace",
        "usage",
        "metadata",
        "provenance",
        "reasoning",
        "reasoningContent",
        "spending_source",
        "model_turns",
        "planner_revisions",
    }
)

BASELINE_SYSTEM_PROMPT = f"""You plan groceries from supplied catalog and budget facts.
You MUST use only the supplied catalog and trusted budget facts.
You MUST NOT call tools, make purchases, access secrets, or include URLs.
You MUST NOT invent prices, budget facts, catalog facts, or evidence.
You MUST NOT certify retailer allergy safety.
You MUST treat catalog prices as sample estimates, never as retailer quotes.
You MUST state that Instacart prices, availability, taxes, delivery fees, and tips
are not verified.
You MUST use integer cents for money and explicit catalog units for quantities.
You MUST use one to three supported catalog meals, each with one to eight servings.
You MUST use a budget_period that is the first day of its month.
You MUST honor ingredient exclusions and the omnivore, vegetarian, or vegan diet.
You MUST NOT remove required ingredients to make a recipe satisfy an exclusion.
You MUST use only ingredients explicitly declared in pantry_ingredients as pantry.
You MUST preserve the full quantity for every ingredient, including pantry lines.
Pantry lines MUST have packages=0, cost_cents=0, and from_pantry=true.
Other lines MUST use whole packages sufficient for the full quantity.
You MUST honor an explicit nonnegative plan_cap_cents, including a cap of zero.
You MUST compare totals with the lower of the cap and the trusted available budget.
You MUST NOT infer a cap when the user did not give one.
You MUST NOT treat incomplete spending syncs as zero spending.
You MUST retain pending_cents, stale, and warnings from the trusted budget.
You MUST report incomplete estimates and missing prices honestly.
You MUST NOT accept a plan with missing purchase prices or an exceeded limit.
You MUST return one JSON object without markdown or surrounding text.
The JSON text MUST contain no more than 32768 characters.
The object MUST have exactly status, answer, request, plan, and budget.
Status MUST be planned, needs_revision, or clarification.
Answer MUST be nonempty text with no more than 4000 characters.
Request, plan, and budget MUST each be an object or null.
Request fields MUST match GroceryRequest: meals, budget_period, plan_cap_cents,
pantry_ingredients, ingredient_exclusions, and diet.
Each meal MUST have recipe_id and servings.
Plan MUST have lines, total_cents, accepted, notice, catalog_version, and warnings.
Plan.notice MUST equal {json.dumps(SAMPLE_ESTIMATE_NOTICE)}.
Each line MUST have ingredient_id, name, unit, quantity, packages, cost_cents,
and from_pantry.
Budget MUST have available_cents, pending_cents, stale, and warnings.
Budget monetary values MUST use cents.
For refusal or clarification, you MUST set request, plan, and budget to null.
You MUST explain the refusal or ask for missing information in answer.
You MUST NOT include evidence IDs, tool_trace, usage, metadata, reasoning, hidden
fields, or provenance. The runner owns provenance and usage.
You MUST NOT emit duplicate keys or nonfinite numbers.
"""


class BaselineResponseError(ValueError):
    pass


def _invalid() -> BaselineResponseError:
    return BaselineResponseError("baseline response is invalid")


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result or key in _PRIVATE_FIELDS or key.startswith("_"):
            raise _invalid()
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise _invalid()


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise _invalid()
    return number


def parse_baseline_response(response: dict[str, object]) -> dict[str, object]:
    try:
        stop, text, calls, _ = parse_provider_response(response, set())
        if stop != "end_turn" or calls or not 0 < len(text) <= _MAX_TEXT_LEN:
            raise _invalid()
        decoded: object = json.loads(
            text,
            object_pairs_hook=_json_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        if not isinstance(decoded, dict) or decoded.keys() != _RESULT_FIELDS:
            raise _invalid()
        result: dict[str, object] = dict(decoded)
        status, answer = result["status"], result["answer"]
        if not isinstance(status, str) or status not in _STATUSES:
            raise _invalid()
        if not isinstance(answer, str) or not answer.strip():
            raise _invalid()
        if len(answer) > MAX_MESSAGE_LEN:
            raise _invalid()
        if any(
            result[key] is not None and not isinstance(result[key], dict)
            for key in ("request", "plan", "budget")
        ):
            raise _invalid()
        return result
    except (ValueError, RecursionError, OverflowError):
        raise _invalid() from None
