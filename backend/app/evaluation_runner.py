from typing import cast

from app.evaluation_budget import evaluate_budget_case
from app.evaluation_followup import evaluate_followup_case
from app.evaluation_meals import evaluate_meal_case
from app.evaluation_missing import evaluate_missing_case
from app.evaluation_protocol import evaluate_protocol_case
from app.evaluation_provider import evaluate_provider_case
from app.evaluation_refresh import evaluate_refresh_case

REPEAT_COUNT = 3
UNASSESSED = "unassessed"


def _as_case(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _case_id(case: dict[str, object]) -> str:
    value = case.get("id")
    return value if type(value) is str else "invalid_case"


def _group(case: dict[str, object]) -> str:
    value = case.get("group")
    return value if type(value) is str else "invalid_group"


def _version(corpus: dict[str, object]) -> str:
    value = corpus.get("version")
    return value if type(value) is str else "invalid_version"


def _metrics_status(corpus: dict[str, object]) -> str:
    value = corpus.get("metrics_status")
    if type(value) is str and value == UNASSESSED:
        return value
    return UNASSESSED


def _dispatch(
    group: str, case: dict[str, object]
) -> tuple[str, dict[str, object] | None]:
    if group == "budget":
        return "scored", evaluate_budget_case(case)
    if group == "meals":
        return "scored", evaluate_meal_case(case)
    if group == "followup" and case.get("requires_model") is False:
        return "scored", evaluate_followup_case(case)
    if group == "missing" and case.get("requires_model") is False:
        return "scored", evaluate_missing_case(case)
    if group == "provider" and case.get("requires_model") is False:
        behavior = _as_case(case.get("fixture_behavior"))
        kind = behavior.get("kind")
        fake = behavior.get("provider") == "fake"
        if kind == "bedrock_unavailable" and fake:
            return "scored", evaluate_provider_case(case)
        if _case_id(case) == "P01" and kind == "plaid_refresh_failure" and fake:
            return "scored", evaluate_refresh_case(case)
        return UNASSESSED, None
    return UNASSESSED, None


def _slot(case: dict[str, object], repeat: int) -> dict[str, object]:
    group = _group(case)
    status, report = _dispatch(group, case)
    slot: dict[str, object] = {
        "case_id": _case_id(case),
        "repeat": repeat,
        "group": group,
        "status": status,
        "report": report,
    }
    behavior = _as_case(case.get("fixture_behavior"))
    if (
        _case_id(case) == "P04"
        and case.get("requires_model") is True
        and behavior.get("kind") == "malformed_or_unknown_tool"
        and behavior.get("provider") == "fake"
    ):
        slot["controlled_report"] = evaluate_protocol_case(case)
    return slot


def run_evaluation(corpus: dict[str, object]) -> dict[str, object]:
    rows = corpus.get("scenarios")
    slots: list[dict[str, object]] = []
    if isinstance(rows, list):
        for item in rows:
            case = _as_case(item)
            for repeat in range(1, REPEAT_COUNT + 1):
                slots.append(_slot(case, repeat))
    return {
        "version": _version(corpus),
        "repeats": REPEAT_COUNT,
        "slot_count": len(slots),
        "slots": slots,
        "metrics_status": _metrics_status(corpus),
    }
