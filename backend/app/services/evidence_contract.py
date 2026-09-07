import json
from typing import Literal, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
)

from app.agent.planning_tool import execute_plan
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.services.plan_job import SpendingInput

_SNAPSHOT_ERROR = "evidence snapshot is invalid"
_USER_ERROR = "user_id is invalid"
_CANONICAL_ERROR = "canonical JSON is invalid"


class EvidenceInputs(BaseModel):
    """Server-normalized budget aggregates. Do not pass raw ledger rows."""

    model_config = ConfigDict(extra="forbid")

    monthly_limit_cents: StrictInt = Field(ge=0)
    spending: SpendingInput
    spending_source: Literal["fixture", "plaid_sandbox"]
    calculated_at: AwareDatetime
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)


def canonical_json(value: object) -> str:
    error: ValueError | None = None
    encoded: str | None = None
    try:
        _reject_bad(value, set())
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        )
    except (RecursionError, TypeError, ValueError):
        error = ValueError(_CANONICAL_ERROR)
    if error is not None:
        raise error
    if encoded is None:
        raise ValueError(_CANONICAL_ERROR)
    return encoded


def _reject_bad(value: object, seen: set[int]) -> None:
    ident = id(value)
    if ident in seen:
        raise ValueError(_CANONICAL_ERROR)
    if isinstance(value, dict):
        seen.add(ident)
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError(_CANONICAL_ERROR)
            _reject_bad(child, seen)
        seen.discard(ident)
        return
    if isinstance(value, list):
        seen.add(ident)
        for child in value:
            _reject_bad(child, seen)
        seen.discard(ident)
        return
    if type(value) not in {bool, float, int, str, type(None)}:
        raise ValueError(_CANONICAL_ERROR)


def _json_object(value: object) -> dict[str, object]:
    copied = json.loads(canonical_json(value))
    if not isinstance(copied, dict):
        raise ValueError(_SNAPSHOT_ERROR)
    return cast(dict[str, object], copied)


def _normalize(
    user_id: int, planning: dict[str, object], inputs: EvidenceInputs
) -> dict[str, object]:
    parsed = EvidenceInputs.model_validate(inputs.model_dump(mode="json"))
    spending = parsed.spending
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            spending.period,
            spending.posted_cents,
            spending.pending_cents,
            spending.refreshed_at,
        ),
        now=parsed.calculated_at,
        plan_cap_cents=parsed.plan_cap_cents,
    )
    recomputed = execute_plan(
        planning["request"],
        budget,
        spending.period,
        user_id=user_id,
        spending_source=parsed.spending_source,
    )
    if canonical_json(planning) != canonical_json(recomputed):
        raise ValueError(_SNAPSHOT_ERROR)
    return _json_object(
        {"planning": recomputed, "budget_inputs": parsed.model_dump(mode="json")}
    )


def normalize_snapshot(
    user_id: int, planning: dict[str, object], inputs: EvidenceInputs
) -> dict[str, object]:
    if type(user_id) is not int or user_id < 1:
        raise ValueError(_USER_ERROR)
    error: ValueError | None = None
    result: dict[str, object] | None = None
    try:
        result = _normalize(user_id, planning, inputs)
    except (AttributeError, KeyError, TypeError, ValidationError, ValueError):
        error = ValueError(_SNAPSHOT_ERROR)
    if error is not None:
        raise error
    if result is None:
        raise ValueError(_SNAPSHOT_ERROR)
    return result
