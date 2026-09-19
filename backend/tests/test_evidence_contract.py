import copy
import json
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
from pydantic import ValidationError

from app.agent.planning_tool import execute_plan
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.services.evidence_contract import (
    EvidenceInputs,
    canonical_json,
    normalize_snapshot,
)
from app.services.plan_job import SpendingInput

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
PERIOD = date(2026, 9, 1)
SECRET = "sk-test-not-for-models"


def spending(**overrides: object) -> SpendingInput:
    values: dict[str, object] = {
        "period": PERIOD,
        "posted_cents": 2_500,
        "pending_cents": 400,
        "refreshed_at": NOW - timedelta(hours=1),
    }
    values.update(overrides)
    return SpendingInput.model_validate(values)


def inputs(**overrides: object) -> EvidenceInputs:
    values: dict[str, object] = {
        "monthly_limit_cents": 10_000,
        "spending": spending(),
        "spending_source": "fixture",
        "calculated_at": NOW,
        "plan_cap_cents": None,
    }
    values.update(overrides)
    return EvidenceInputs.model_validate(values)


def request_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def genuine_planning(
    user_id: int = 1,
    evidence_inputs: EvidenceInputs | None = None,
    **request_overrides: object,
) -> dict[str, object]:
    parsed = evidence_inputs or inputs()
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            parsed.spending.period,
            parsed.spending.posted_cents,
            parsed.spending.pending_cents,
            parsed.spending.refreshed_at,
        ),
        now=parsed.calculated_at,
        plan_cap_cents=parsed.plan_cap_cents,
    )
    return execute_plan(
        request_payload(**request_overrides),
        budget,
        parsed.spending.period,
        user_id=user_id,
        spending_source=parsed.spending_source,
    )


def assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_canonical_json_is_sorted_compact_and_rejects_bad_values() -> None:
    encoded = canonical_json({"b": 1, "a": [True, None]})
    assert encoded == '{"a":[true,null],"b":1}'
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="canonical JSON is invalid") as cyclic_error:
        canonical_json(cyclic)
    assert_static(cyclic_error.value, "self")
    with pytest.raises(ValueError, match="canonical JSON is invalid"):
        canonical_json({1: "a"})
    with pytest.raises(ValueError, match="canonical JSON is invalid"):
        canonical_json({"n": float("nan")})
    with pytest.raises(ValueError, match="canonical JSON is invalid"):
        canonical_json((1, 2))
    nested: object = None
    for _ in range(2000):
        nested = [nested]
    with pytest.raises(ValueError, match="canonical JSON is invalid") as nested_error:
        canonical_json(nested)
    assert_static(nested_error.value, "maximum recursion depth")


def test_evidence_inputs_forbid_extra_and_non_strict_cents() -> None:
    with pytest.raises(ValidationError):
        inputs(unexpected="value")
    with pytest.raises(ValidationError):
        inputs(monthly_limit_cents=True)
    with pytest.raises(ValidationError):
        inputs(plan_cap_cents=True)
    with pytest.raises(ValidationError):
        inputs(monthly_limit_cents=-1)
    with pytest.raises(ValidationError):
        inputs(spending_source="live")


def test_genuine_execute_plan_roundtrip_copies_json_and_skips_mutation() -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    original_planning = copy.deepcopy(planning)
    original_inputs = parsed.model_dump()
    snapshot = normalize_snapshot(1, planning, parsed)
    assert set(snapshot) == {"planning", "budget_inputs"}
    assert snapshot["planning"] == planning
    assert snapshot["budget_inputs"] == parsed.model_dump(mode="json")
    assert json.loads(json.dumps(snapshot, allow_nan=False)) == snapshot
    assert planning == original_planning
    assert parsed.model_dump() == original_inputs
    loaded = snapshot["planning"]
    assert isinstance(loaded, dict)
    loaded["extra"] = SECRET
    assert "extra" not in planning


def test_forged_accepted_cost_source_metadata_and_id_are_rejected() -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    plan = cast(dict[str, object], copy.deepcopy(planning["plan"]))
    cases: list[dict[str, object]] = []
    accepted = copy.deepcopy(planning)
    plan["accepted"] = not bool(plan["accepted"])
    accepted["plan"] = plan
    cases.append(accepted)
    cost = copy.deepcopy(planning)
    cost_plan = cast(dict[str, object], copy.deepcopy(planning["plan"]))
    cost_plan["total_cents"] = 1
    cost["plan"] = cost_plan
    cases.append(cost)
    source = copy.deepcopy(planning)
    source["spending_source"] = "plaid_sandbox"
    cases.append(source)
    extra = copy.deepcopy(planning)
    extra["metadata"] = {"token": SECRET}
    cases.append(extra)
    existing = copy.deepcopy(planning)
    existing["evidence_id"] = "grocery-deadbeef:user-1:2026-09"
    cases.append(existing)
    as_int = copy.deepcopy(planning)
    int_plan = cast(dict[str, object], copy.deepcopy(planning["plan"]))
    int_plan["accepted"] = 1 if int_plan["accepted"] is True else 0
    as_int["plan"] = int_plan
    cases.append(as_int)
    for forged in cases:
        with pytest.raises(ValueError, match="evidence snapshot is invalid") as caught:
            normalize_snapshot(1, forged, parsed)
        assert_static(caught.value, SECRET)
        assert_static(caught.value, "deadbeef")
        assert_static(caught.value, "plaid_sandbox")


def test_stale_cap_refund_and_period_inputs() -> None:
    stale = inputs(
        spending=spending(refreshed_at=NOW - timedelta(hours=25)),
    )
    with pytest.raises(ValueError, match="evidence snapshot is invalid") as stale_error:
        normalize_snapshot(1, genuine_planning(evidence_inputs=inputs()), stale)
    assert_static(stale_error.value, "stale")
    capped = inputs(
        spending=spending(refreshed_at=NOW - timedelta(hours=25)),
        plan_cap_cents=100,
    )
    snapshot = normalize_snapshot(1, genuine_planning(evidence_inputs=capped), capped)
    planning = snapshot["planning"]
    assert isinstance(planning, dict)
    budget = planning["budget"]
    assert isinstance(budget, dict)
    assert budget["available_cents"] == 100
    refund = inputs(spending=spending(posted_cents=-250))
    refund_snapshot = normalize_snapshot(
        1, genuine_planning(evidence_inputs=refund), refund
    )
    refund_planning = refund_snapshot["planning"]
    assert isinstance(refund_planning, dict)
    refund_budget = refund_planning["budget"]
    assert isinstance(refund_budget, dict)
    assert refund_budget["available_cents"] == 10_250
    wrong_period = inputs(spending=spending(period=date(2026, 8, 1)))
    with pytest.raises(
        ValueError, match="evidence snapshot is invalid"
    ) as period_error:
        normalize_snapshot(1, genuine_planning(evidence_inputs=inputs()), wrong_period)
    assert_static(period_error.value, "2026-08-01")


def test_cap_mismatch_and_unsafe_constraint_are_static() -> None:
    parsed = inputs(plan_cap_cents=0)
    planning = genuine_planning(evidence_inputs=inputs())
    with pytest.raises(ValueError, match="evidence snapshot is invalid") as cap_error:
        normalize_snapshot(1, planning, parsed)
    assert_static(cap_error.value, "0")
    unsafe = copy.deepcopy(genuine_planning(evidence_inputs=inputs()))
    request = cast(dict[str, object], copy.deepcopy(unsafe["request"]))
    request["pantry_ingredients"] = ["not_in_catalog"]
    unsafe["request"] = request
    with pytest.raises(
        ValueError, match="evidence snapshot is invalid"
    ) as unsafe_error:
        normalize_snapshot(1, unsafe, inputs())
    assert_static(unsafe_error.value, "not_in_catalog")


def test_changed_macro_totals_are_rejected() -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    forged = copy.deepcopy(planning)
    nutrition = cast(dict[str, object], copy.deepcopy(forged["meal_nutrition"]))
    total = cast(dict[str, object], nutrition["total"])
    energy = total["energy_kcal"]
    assert type(energy) is int
    total["energy_kcal"] = energy + 1
    nutrition["total"] = total
    forged["meal_nutrition"] = nutrition
    with pytest.raises(ValueError, match="evidence snapshot is invalid") as caught:
        normalize_snapshot(1, forged, parsed)
    assert_static(caught.value, SECRET)
    assert_static(caught.value, str(energy + 1))


@pytest.mark.parametrize("user_id", [0, -1, True])
def test_owner_must_be_a_positive_exact_int(user_id: object) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    with pytest.raises(ValueError, match="user_id is invalid") as caught:
        normalize_snapshot(user_id, planning, parsed)  # type: ignore[arg-type]
    assert_static(caught.value, str(user_id))
