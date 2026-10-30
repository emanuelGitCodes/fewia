import json
from typing import cast

import pytest

from app.agent.estimate import priced_estimate
from app.agent.proposal_tool import (
    PROPOSAL_TOOL,
    ProposalToolError,
    execute_propose,
    proposal_tool_spec,
)
from app.domain.budget import BudgetResult
from app.domain.plan_proposal import INVALID_PROPOSAL_MESSAGE, ProposalInvalid
from app.domain.plan_revision import PlanRevisionInput

_BUDGET = BudgetResult(10_000, 0, False, ())
_SECRET = "do-not-echo-raw-input"
_BEANS = "black_beans"
_ADD: dict[str, object] = {"op": "add", "recipe_id": "vegetable_pasta", "servings": 3}


def _plan(pantry: list[str] | None = None) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "snapshot": {
                "meals": [
                    {"recipe_id": "chicken_tacos", "servings": 2},
                    {"recipe_id": "bean_tacos", "servings": 2},
                ],
                "pantry_ingredient_ids": [] if pantry is None else pantry,
                "plan_cap_cents": 5_000,
            },
        }
    )


class Proposer:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, object]]] = []

    def __call__(self, operations: list[dict[str, object]]) -> str:
        self.calls.append(operations)
        return "proposal-1"


def _run(
    *ops: dict[str, object], proposer: Proposer | None = None
) -> dict[str, object]:
    propose = Proposer() if proposer is None else proposer
    return execute_propose({"operations": list(ops)}, _BUDGET, _plan(), propose)


def _side(payload: dict[str, object], name: str) -> dict[str, object]:
    return cast(dict[str, object], payload[name])


def _walk(value: object) -> list[object]:
    if isinstance(value, dict):
        return [value, *(item for v in value.values() for item in _walk(v))]
    if isinstance(value, list):
        return [item for v in value for item in _walk(v)]
    return [value]


def test_spec_names_the_tool_and_bounds_the_operations() -> None:
    spec = cast(dict[str, dict[str, object]], proposal_tool_spec())["toolSpec"]
    assert spec["name"] == PROPOSAL_TOOL == "propose_plan_change"
    schema = cast(dict[str, dict[str, object]], spec["inputSchema"])["json"]
    assert schema["required"] == ["operations"]
    assert schema["additionalProperties"] is False
    operations = cast(dict[str, object], schema["properties"])["operations"]
    assert isinstance(operations, dict)
    assert (operations["minItems"], operations["maxItems"]) == (1, 6)
    item = cast(dict[str, object], operations["items"])
    properties = cast(dict[str, dict[str, object]], item["properties"])
    assert properties["op"]["enum"] == ["add", "remove", "set_servings", "set_pantry"]
    assert "substitute" not in json.dumps(properties["op"])


def test_spec_uses_plain_types_and_never_says_the_plan_changed() -> None:
    spec = proposal_tool_spec()
    for node in _walk(spec):
        if isinstance(node, dict) and "type" in node:
            assert isinstance(node["type"], str)
    tool_spec = cast(dict[str, dict[str, object]], spec)["toolSpec"]
    description = str(tool_spec["description"])
    assert description.startswith(
        "Use this, not plan_groceries, to add, remove, or resize meals in the "
        "user's saved plan (plan_meals) or to mark pantry items."
    )
    assert "for the user to apply" in description
    assert "never changes the plan" in description
    assert "plan changed" not in description.lower()


@pytest.mark.parametrize(
    ("op", "after_meals"),
    [
        (_ADD, [("chicken_tacos", 2), ("bean_tacos", 2), ("vegetable_pasta", 3)]),
        ({"op": "remove", "recipe_id": "bean_tacos"}, [("chicken_tacos", 2)]),
        (
            {"op": "set_servings", "recipe_id": "bean_tacos", "servings": 4},
            [("chicken_tacos", 2), ("bean_tacos", 4)],
        ),
        (
            {"op": "set_pantry", "ingredient_id": _BEANS, "owned": True},
            [("chicken_tacos", 2), ("bean_tacos", 2)],
        ),
    ],
    ids=["add", "remove", "set_servings", "set_pantry"],
)
def test_payload_carries_operations_and_before_and_after(
    op: dict[str, object], after_meals: list[tuple[str, int]]
) -> None:
    proposer = Proposer()
    payload = _run(op, proposer=proposer)
    assert proposer.calls == [[op]]
    assert payload["status"] == "proposed"
    assert payload["proposal_id"] == "proposal-1"
    assert payload["operations"] == [op]
    before, after = _side(payload, "before"), _side(payload, "after")
    base = [("chicken_tacos", 2), ("bean_tacos", 2)]
    pantry = [_BEANS] if op["op"] == "set_pantry" else []
    assert before["meals"] == [{"recipe_id": r, "servings": s} for r, s in base]
    assert after["meals"] == [{"recipe_id": r, "servings": s} for r, s in after_meals]
    assert before["estimate"] == priced_estimate(base, [], _BUDGET, 5_000)
    assert after["estimate"] == priced_estimate(after_meals, pantry, _BUDGET, 5_000)
    for side, meals in ((before, base), (after, after_meals)):
        nutrition = cast(list[dict[str, object]], side["nutrition"])
        assert [item["recipe_id"] for item in nutrition] == [r for r, _ in meals]
        for item in nutrition:
            per_serving = cast(dict[str, object], item["per_serving"])
            assert {"energy_kcal", "protein_mg"} <= set(per_serving)
    json.dumps(payload)


def test_several_operations_are_applied_in_order() -> None:
    payload = _run(
        _ADD,
        {"op": "remove", "recipe_id": "bean_tacos"},
        {"op": "set_servings", "recipe_id": "chicken_tacos", "servings": 4},
    )
    assert _side(payload, "after")["meals"] == [
        {"recipe_id": "chicken_tacos", "servings": 4},
        {"recipe_id": "vegetable_pasta", "servings": 3},
    ]


def test_the_tool_leaves_the_plan_revision_unchanged() -> None:
    plan = _plan()
    before = plan.model_dump(mode="json")
    execute_propose({"operations": [_ADD]}, _BUDGET, plan, Proposer())
    assert plan.model_dump(mode="json") == before


@pytest.mark.parametrize(
    "arguments",
    [
        {"operations": []},
        {"operations": [{"op": "remove", "recipe_id": "bean_tacos"}] * 7},
        {"operations": [{"op": "remove", "recipe_id": "not_a_meal"}]},
        {"operations": [{"op": "add", "recipe_id": "chicken_tacos", "servings": 1}]},
        {"operations": [{"op": "add", "recipe_id": "vegetable_pasta", "servings": 9}]},
        {
            "operations": [
                {"op": "set_servings", "recipe_id": "bean_tacos", "servings": 0}
            ]
        },
        {"operations": [{"op": "set_pantry", "ingredient_id": "nope", "owned": True}]},
        {"operations": [{"op": "set_pantry", "ingredient_id": _BEANS, "owned": 1}]},
        {"operations": [{"op": "substitute", "recipe_id": "bean_tacos"}]},
        {"operations": [{"op": "remove", "recipe_id": "bean_tacos", "extra": 1}]},
        {
            "operations": [
                {"op": "remove", "recipe_id": "bean_tacos"},
                {"op": "remove", "recipe_id": "chicken_tacos"},
            ]
        },
        {"operations": [_ADD], "extra": 1},
        {},
        {"operations": "remove"},
        [],
        None,
        "operations",
    ],
)
def test_invalid_arguments_store_nothing_and_give_the_fixed_message(
    arguments: object,
) -> None:
    proposer = Proposer()
    with pytest.raises(ProposalToolError) as caught:
        execute_propose(arguments, _BUDGET, _plan(), proposer)
    assert str(caught.value) == INVALID_PROPOSAL_MESSAGE
    assert caught.value.__cause__ is None
    assert proposer.calls == []


def test_the_error_never_echoes_model_text() -> None:
    proposer = Proposer()
    with pytest.raises(ProposalToolError) as caught:
        execute_propose(
            {"operations": [{"op": "remove", "recipe_id": _SECRET}]},
            _BUDGET,
            _plan(),
            proposer,
        )
    assert _SECRET not in str(caught.value)
    assert _SECRET not in repr(caught.value.args)
    assert proposer.calls == []


def test_a_payload_build_failure_stores_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object) -> dict[str, object]:
        raise RuntimeError("build failed")

    monkeypatch.setattr("app.agent.proposal_tool._side", broken)
    proposer = Proposer()
    with pytest.raises(RuntimeError):
        execute_propose({"operations": [_ADD]}, _BUDGET, _plan(), proposer)
    assert proposer.calls == []


def test_a_proposer_rejection_becomes_the_fixed_tool_error() -> None:
    def refuse(_: list[dict[str, object]]) -> str:
        raise ProposalInvalid(_SECRET)

    with pytest.raises(ProposalToolError) as caught:
        execute_propose({"operations": [_ADD]}, _BUDGET, _plan(), refuse)
    assert str(caught.value) == INVALID_PROPOSAL_MESSAGE
    assert _SECRET not in str(caught.value)
