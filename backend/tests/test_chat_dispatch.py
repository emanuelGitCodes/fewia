import json
from datetime import date
from typing import cast, get_args

import pytest

from app.agent.budget_tool import (
    TOOL_NAME as BUDGET_TOOL_NAME,
)
from app.agent.budget_tool import (
    execute_budget_summary,
)
from app.agent.chat_dispatch import dispatch
from app.agent.chat_messages import ChatProtocolError, ToolCall
from app.agent.planning_tool import TOOL_NAME, PlanningToolError, execute_plan
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, Diet

PERIOD = date(2026, 9, 1)
_SECRET = "do-not-echo-raw-input"
_REV = "a" * 64


def _error_trace(
    tool: str,
    tool_use_id: str,
    *,
    sequence: int = 1,
    revision_index: int | None = 1,
) -> dict[str, object]:
    return {
        "tool": tool,
        "outcome": "error",
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": revision_index,
    }


def _success_trace(
    tool_use_id: str,
    evidence_id: object,
    *,
    sequence: int = 1,
    revision_index: int = 1,
    revision_id: str | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": TOOL_NAME,
        "outcome": "success",
        "evidence_id": evidence_id,
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": revision_index,
    }
    if revision_id is not None:
        entry["evidence_revision_id"] = revision_id
    return entry


def arguments(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def _tool_json(block: dict[str, object]) -> dict[str, object]:
    result = block["toolResult"]
    assert isinstance(result, dict)
    content = result["content"]
    assert isinstance(content, list)
    first = content[0]
    assert isinstance(first, dict)
    body = first["json"]
    assert isinstance(body, dict)
    return body


def test_valid_plan_returns_payload_and_matching_tool_result_id() -> None:
    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    expected = execute_plan(arguments(), budget(), PERIOD)
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate == expected
    assert candidate is not None
    assert block["toolResult"]["toolUseId"] == "call-1"
    assert block["toolResult"]["status"] == "success"
    json_body = _tool_json(block)
    plan = expected["plan"]
    budget_payload = expected["budget"]
    assert isinstance(plan, dict)
    assert isinstance(budget_payload, dict)
    assert json_body["plan"] == plan
    assert json_body["budget"] == budget_payload
    assert json_body["evidence_id"] == expected["evidence_id"]
    assert json_body["currency"] == "USD"
    assert json_body["money_unit"] == "cents"
    assert json_body["money_display"] == {
        "total": _usd(cast(int, plan["total_cents"])),
        "available": _usd(cast(int, budget_payload["available_cents"])),
        "pending": _usd(cast(int, budget_payload["pending_cents"])),
    }
    evidence = expected["evidence_id"]
    assert isinstance(evidence, str)
    assert trace == [_success_trace("call-1", evidence)]
    assert "evidence_revision_id" not in expected
    assert "evidence_revision_id" not in candidate
    assert "currency" not in candidate
    assert "money_unit" not in candidate
    assert "money_display" not in candidate
    assert "evidence_revision_id" not in json_body


def test_unknown_name_returns_unsupported_and_clears_candidate() -> None:
    call = ToolCall("call-9", "purchase_items", {"token": _SECRET})
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-9",
            "content": [{"json": {"error": "unsupported tool"}}],
            "status": "error",
        }
    }
    assert trace == [_error_trace("unsupported", "call-9", revision_index=None)]
    assert set(trace[0]) == {
        "tool",
        "outcome",
        "tool_use_id",
        "sequence",
        "revision_index",
    }


def test_invalid_args_return_static_error_and_clear_candidate() -> None:
    args = arguments(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    call = ToolCall("call-2", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-2",
            "content": [{"json": {"error": "arguments are invalid"}}],
            "status": "error",
        }
    }
    assert trace == [_error_trace(TOOL_NAME, "call-2")]
    assert set(trace[0]) == {
        "tool",
        "outcome",
        "tool_use_id",
        "sequence",
        "revision_index",
    }


def test_capped_budget_uses_smaller_plan_cap() -> None:
    args = arguments(plan_cap_cents=100)
    call = ToolCall("call-3", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(1_000), PERIOD, 1, "fixture", trace)
    assert candidate is not None
    budget_payload = candidate["budget"]
    plan_payload = candidate["plan"]
    assert isinstance(budget_payload, dict)
    assert isinstance(plan_payload, dict)
    assert budget_payload["available_cents"] == 100
    assert plan_payload["accepted"] is False
    assert block["toolResult"]["toolUseId"] == "call-3"
    assert block["toolResult"]["status"] == "success"
    assert trace[0]["tool"] == TOOL_NAME
    assert trace[0]["outcome"] == "success"
    assert trace[0]["tool_use_id"] == "call-3"
    assert trace[0]["sequence"] == 1
    assert trace[0]["revision_index"] == 1
    assert "evidence_revision_id" not in trace[0]


def test_errors_omit_raw_input_and_exception_context() -> None:
    args = arguments(meals=[{"recipe_id": _SECRET, "servings": 1}])
    call = ToolCall("call-4", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    dumped = json.dumps({"block": block, "trace": trace})
    assert _SECRET not in dumped
    assert "ValidationError" not in dumped
    assert "PlanningToolError" not in dumped
    assert "Traceback" not in dumped
    assert block["toolResult"]["content"] == [
        {
            "json": {
                "error": "recipe is not supported",
                "error_code": "unsupported_recipe",
                "supported_recipe_ids": list(SUPPORTED_RECIPE_IDS),
            }
        }
    ]
    unknown = ToolCall("call-5", "purchase_items", {"token": _SECRET})
    unknown_trace: list[dict[str, object]] = []
    unknown_candidate, unknown_block = dispatch(
        unknown, budget(), PERIOD, 1, "fixture", unknown_trace
    )
    assert unknown_candidate is None
    unknown_dump = json.dumps({"block": unknown_block, "trace": unknown_trace})
    assert _SECRET not in unknown_dump
    assert "purchase_items" not in unknown_dump


def test_record_evidence_sees_plain_payload_before_injection() -> None:
    expected = execute_plan(arguments(), budget(), PERIOD)
    seen: list[dict[str, object]] = []
    held: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(dict(payload))
        held.append(payload)
        assert "evidence_revision_id" not in payload
        return _REV

    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(
        call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    assert seen == [expected]
    assert candidate is held[0]
    assert candidate is not None
    assert candidate["evidence_revision_id"] == _REV
    assert "evidence_revision_id" not in seen[0]
    assert "currency" not in seen[0]
    assert "money_display" not in seen[0]
    assert "currency" not in candidate
    assert "money_display" not in candidate
    json_body = _tool_json(block)
    assert json_body["evidence_revision_id"] == _REV
    assert json_body["currency"] == "USD"
    assert json_body["money_unit"] == "cents"
    assert "money_display" in json_body
    assert trace == [
        _success_trace("call-1", expected["evidence_id"], revision_id=_REV)
    ]


def test_over_budget_plan_can_record_evidence() -> None:
    args = arguments(plan_cap_cents=100)
    expected = execute_plan(args, budget(1_000), PERIOD)

    def record(payload: dict[str, object]) -> str:
        plan_payload = payload["plan"]
        assert isinstance(plan_payload, dict)
        assert plan_payload["accepted"] is False
        assert "evidence_revision_id" not in payload
        return _REV

    call = ToolCall("call-3", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(
        call, budget(1_000), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    assert candidate is not None
    assert candidate["evidence_id"] == expected["evidence_id"]
    assert candidate["evidence_revision_id"] == _REV
    assert block["toolResult"]["status"] == "success"
    assert trace[0]["evidence_revision_id"] == _REV
    assert trace[0]["revision_index"] == 1


def test_recorder_is_not_called_for_invalid_or_unsupported() -> None:
    calls: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        calls.append(payload)
        return _REV

    bad = arguments(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    trace: list[dict[str, object]] = []
    invalid, _block = dispatch(
        ToolCall("call-2", TOOL_NAME, bad),
        budget(),
        PERIOD,
        1,
        "fixture",
        trace,
        record_evidence=record,
    )
    unknown, _unknown_block = dispatch(
        ToolCall("call-9", "purchase_items", {"token": _SECRET}),
        budget(),
        PERIOD,
        1,
        "fixture",
        trace,
        record_evidence=record,
    )
    assert invalid is None
    assert unknown is None
    assert calls == []
    assert trace == [
        _error_trace(TOOL_NAME, "call-2"),
        _error_trace("unsupported", "call-9", sequence=2, revision_index=None),
    ]


def test_record_evidence_error_aborts_without_success_trace() -> None:
    def record(payload: dict[str, object]) -> str:
        raise RuntimeError("store-failed")

    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    with pytest.raises(RuntimeError, match="store-failed") as caught:
        dispatch(call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "ValidationError" not in str(caught.value)
    assert trace == []


def test_invalid_record_id_is_static_failure() -> None:
    static = "evidence revision id is invalid"
    cases: list[object] = ["", "A" * 64, "a" * 63, "a" * 65, "g" + "a" * 63, None]

    for value in cases:
        call = ToolCall("call-1", TOOL_NAME, arguments())
        trace: list[dict[str, object]] = []

        def record(payload: dict[str, object], returned: object = value) -> str:
            return cast(str, returned)

        with pytest.raises(ChatProtocolError, match=static) as caught:
            dispatch(
                call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
            )
        assert str(caught.value) == static
        if isinstance(value, str) and value:
            assert value not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert trace == []


def test_repeated_revision_id_keeps_ordered_occurrences() -> None:
    def record(payload: dict[str, object]) -> str:
        return _REV

    first = ToolCall("a", TOOL_NAME, arguments())
    second = ToolCall("b", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    first_plan, _first_block = dispatch(
        first, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    second_plan, _second_block = dispatch(
        second, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    evidence = execute_plan(arguments(), budget(), PERIOD)["evidence_id"]
    assert first_plan is not None
    assert second_plan is not None
    assert first_plan["evidence_revision_id"] == _REV
    assert second_plan["evidence_revision_id"] == _REV
    assert trace == [
        _success_trace("a", evidence, revision_id=_REV),
        _success_trace("b", evidence, sequence=2, revision_index=2, revision_id=_REV),
    ]
    dumped = json.dumps(trace)
    assert "chicken_tacos" not in dumped
    assert "meals" not in dumped
    assert "reasoningContent" not in dumped


def test_llm_tool_result_formats_usd_without_mutating_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, object] = {"total_cents": 1703, "accepted": True}
    budget_payload: dict[str, object] = {
        "available_cents": 4000,
        "pending_cents": -50,
    }
    fake_payload: dict[str, object] = {
        "request": {},
        "plan": plan,
        "budget": budget_payload,
        "spending_source": "fixture",
        "evidence_id": "ev-1703",
    }
    recorded: list[dict[str, object]] = []

    def fake_execute(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        return fake_payload

    def record(payload: dict[str, object]) -> str:
        recorded.append(payload)
        return _REV

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute)
    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(
        call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    assert candidate is fake_payload
    assert recorded == [fake_payload]
    assert candidate["plan"] is plan
    assert candidate["budget"] is budget_payload
    assert plan == {"total_cents": 1703, "accepted": True}
    assert budget_payload == {"available_cents": 4000, "pending_cents": -50}
    assert "currency" not in candidate
    assert "money_unit" not in candidate
    assert "money_display" not in candidate
    json_body = _tool_json(block)
    assert json_body is not candidate
    assert json_body["plan"] is plan
    assert json_body["budget"] is budget_payload
    assert json_body["currency"] == "USD"
    assert json_body["money_unit"] == "cents"
    assert json_body["money_display"] == {
        "total": "USD $17.03",
        "available": "USD $40.00",
        "pending": "USD -$0.50",
    }
    assert json_body["evidence_revision_id"] == _REV
    assert candidate["evidence_revision_id"] == _REV


def test_missing_total_stays_unknown_and_does_not_become_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, object] = {"total_cents": None, "accepted": False}
    budget_payload: dict[str, object] = {"pending_cents": 250}
    fake_payload: dict[str, object] = {
        "request": {},
        "plan": plan,
        "budget": budget_payload,
        "spending_source": "fixture",
        "evidence_id": "ev-missing",
    }

    def fake_execute(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        return fake_payload

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute)
    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is fake_payload
    assert "currency" not in candidate
    assert "money_display" not in candidate
    json_body = _tool_json(block)
    display = json_body["money_display"]
    assert isinstance(display, dict)
    assert display["total"] == "unknown"
    assert "available" not in display
    assert display["pending"] == "USD $2.50"
    assert display.get("total") != "USD $0.00"
    assert "available_cents" not in budget_payload


def test_unsupported_recipe_returns_static_typed_tool_error() -> None:
    args = arguments(meals=[{"recipe_id": "sushi", "servings": 1}])
    call = ToolCall("call-unknown-recipe", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-unknown-recipe",
            "content": [
                {
                    "json": {
                        "error": "recipe is not supported",
                        "error_code": "unsupported_recipe",
                        "supported_recipe_ids": list(SUPPORTED_RECIPE_IDS),
                    }
                }
            ],
            "status": "error",
        }
    }
    assert trace == [_error_trace(TOOL_NAME, "call-unknown-recipe")]
    assert set(trace[0]) == {
        "tool",
        "outcome",
        "tool_use_id",
        "sequence",
        "revision_index",
    }
    dumped = json.dumps({"block": block, "trace": trace})
    assert "PlanningToolError" not in dumped
    assert "sushi" not in dumped


def test_unsupported_recipe_with_invalid_servings_returns_invalid_args() -> None:
    args = arguments(meals=[{"recipe_id": "sushi", "servings": 9}])
    call = ToolCall("call-mix", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-mix",
            "content": [{"json": {"error": "arguments are invalid"}}],
            "status": "error",
        }
    }
    assert trace == [_error_trace(TOOL_NAME, "call-mix")]
    dumped = json.dumps({"block": block, "trace": trace})
    assert "PlanningToolError" not in dumped
    assert "sushi" not in dumped
    assert "unsupported_recipe" not in dumped


def test_unsupported_diet_returns_static_typed_tool_error() -> None:
    unknown = "<script>do-not-echo-raw-input</script>"
    args = arguments(diet=unknown)
    call = ToolCall("call-unknown-diet", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-unknown-diet",
            "content": [
                {
                    "json": {
                        "error": "diet is not supported",
                        "error_code": "unsupported_diet",
                        "supported_diets": list(get_args(Diet)),
                    }
                }
            ],
            "status": "error",
        }
    }
    assert list(get_args(Diet)) == ["omnivore", "vegetarian", "vegan"]
    assert trace == [_error_trace(TOOL_NAME, "call-unknown-diet")]
    dumped = json.dumps({"block": block, "trace": trace})
    assert "PlanningToolError" not in dumped
    assert unknown not in dumped
    assert "ValidationError" not in dumped


def test_unsupported_diet_with_invalid_servings_returns_invalid_args() -> None:
    args = arguments(
        diet="keto",
        meals=[{"recipe_id": "chicken_tacos", "servings": 9}],
    )
    call = ToolCall("call-diet-mix", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-diet-mix",
            "content": [{"json": {"error": "arguments are invalid"}}],
            "status": "error",
        }
    }
    dumped = json.dumps({"block": block, "trace": trace})
    assert "keto" not in dumped
    assert "unsupported_diet" not in dumped


def test_unknown_pantry_ingredient_returns_static_typed_tool_error() -> None:
    unknown = "<script>do-not-echo-raw-input</script>"
    args = arguments(pantry_ingredients=[unknown, "also_unknown"])
    call = ToolCall("call-unknown-pantry", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    json_body = {
        "error": "ingredient is not supported",
        "error_code": "unsupported_ingredient",
        "field": "pantry_ingredients",
        "supported_ingredient_ids": list(INGREDIENTS),
    }
    assert block == {
        "toolResult": {
            "toolUseId": "call-unknown-pantry",
            "content": [{"json": json_body}],
            "status": "error",
        }
    }
    assert set(json_body) == {
        "error",
        "error_code",
        "field",
        "supported_ingredient_ids",
    }
    dumped = json.dumps({"block": block, "trace": trace})
    assert unknown not in dumped
    assert "also_unknown" not in dumped
    assert "PlanningToolError" not in dumped
    assert "unknown pantry" not in dumped


def test_unknown_exclusion_ingredient_returns_static_typed_tool_error() -> None:
    unknown = "<script>do-not-echo-raw-input</script>"
    args = arguments(
        pantry_ingredients=["salt"],
        ingredient_exclusions=[unknown, "also_unknown"],
    )
    call = ToolCall("call-unknown-exclusion", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    json_body = _tool_json(block)
    assert json_body == {
        "error": "ingredient is not supported",
        "error_code": "unsupported_ingredient",
        "field": "ingredient_exclusions",
        "supported_ingredient_ids": list(INGREDIENTS),
    }
    dumped = json.dumps({"block": block, "trace": trace})
    assert unknown not in dumped
    assert "also_unknown" not in dumped


def test_unknown_pantry_takes_priority_over_unknown_exclusion() -> None:
    args = arguments(
        pantry_ingredients=["not_in_catalog"],
        ingredient_exclusions=["also_unknown"],
    )
    call = ToolCall("call-priority", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    json_body = _tool_json(block)
    assert json_body["error_code"] == "unsupported_ingredient"
    assert json_body["field"] == "pantry_ingredients"
    dumped = json.dumps({"block": block, "trace": trace})
    assert "not_in_catalog" not in dumped
    assert "also_unknown" not in dumped


def test_unsupported_ingredient_with_invalid_field_returns_invalid_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise PlanningToolError(
            "ingredient is not supported",
            error_code="unsupported_ingredient",
            detail={"field": "meals", "ingredient_id": "onion"},
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute)
    call = ToolCall("call-bad-field", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    dumped = json.dumps({"block": block, "trace": trace})
    assert "onion" not in dumped
    assert "meals" not in dumped
    assert "unsupported_ingredient" not in dumped


def test_exclusion_conflict_returns_static_typed_tool_error() -> None:
    args = arguments(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )
    call = ToolCall("call-ex", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-ex",
            "content": [
                {
                    "json": {
                        "error": "ingredient is excluded",
                        "error_code": "exclusion_reject",
                        "recipe_id": "vegetable_pasta",
                        "ingredient_id": "onion",
                    }
                }
            ],
            "status": "error",
        }
    }
    assert trace == [_error_trace(TOOL_NAME, "call-ex")]
    dumped = json.dumps({"block": block, "trace": trace})
    assert "PlanningToolError" not in dumped


def test_recorder_is_not_called_for_exclusion_conflict() -> None:
    calls: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        calls.append(payload)
        return _REV

    args = arguments(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )
    trace: list[dict[str, object]] = []
    candidate, _block = dispatch(
        ToolCall("call-ex", TOOL_NAME, args),
        budget(),
        PERIOD,
        1,
        "fixture",
        trace,
        record_evidence=record,
    )
    assert candidate is None
    assert calls == []
    assert trace == [_error_trace(TOOL_NAME, "call-ex")]


def test_exclusion_reject_with_invalid_detail_returns_invalid_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise PlanningToolError(
            "ingredient is excluded",
            error_code="exclusion_reject",
            detail=cast(
                dict[str, str],
                {"recipe_id": "vegetable_pasta", "ingredient_id": 1},
            ),
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute)
    call = ToolCall("call-bad", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    assert trace == [_error_trace(TOOL_NAME, "call-bad")]


def test_other_planning_tool_error_returns_invalid_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exclusion_shaped = {"recipe_id": "vegetable_pasta", "ingredient_id": "onion"}

    def fake_execute(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise PlanningToolError(
            "budget is invalid",
            error_code="budget_invalid",
            detail=exclusion_shaped,
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute)
    call = ToolCall("call-other", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    assert trace == [_error_trace(TOOL_NAME, "call-other")]

    def fake_execute_none(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise PlanningToolError(
            "budget is invalid",
            error_code=None,
            detail=exclusion_shaped,
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute_none)
    none_trace: list[dict[str, object]] = []
    none_candidate, none_block = dispatch(
        ToolCall("call-none", TOOL_NAME, arguments()),
        budget(),
        PERIOD,
        1,
        "fixture",
        none_trace,
    )
    assert none_candidate is None
    assert none_block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    assert none_trace == [_error_trace(TOOL_NAME, "call-none")]

    def fake_execute_partial(
        _arguments: object,
        _budget: BudgetResult,
        _period: date,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise PlanningToolError(
            "ingredient is excluded",
            error_code="exclusion_reject",
            detail={"recipe_id": "vegetable_pasta"},
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_plan", fake_execute_partial)
    partial_trace: list[dict[str, object]] = []
    partial_candidate, partial_block = dispatch(
        ToolCall("call-partial", TOOL_NAME, arguments()),
        budget(),
        PERIOD,
        1,
        "fixture",
        partial_trace,
    )
    assert partial_candidate is None
    assert partial_block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    assert partial_trace == [_error_trace(TOOL_NAME, "call-partial")]


def test_budget_summary_success_skips_recorder_and_omits_evidence() -> None:
    expected = execute_budget_summary({}, budget(), PERIOD, spending_source="fixture")
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(payload)
        return _REV

    call = ToolCall("sum-1", BUDGET_TOOL_NAME, {})
    trace: list[dict[str, object]] = []
    payload, block = dispatch(
        call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    assert payload == expected
    assert seen == []
    assert block["toolResult"]["toolUseId"] == "sum-1"
    assert block["toolResult"]["status"] == "success"
    assert _tool_json(block) == expected
    assert trace == [
        {
            "tool": BUDGET_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "sum-1",
            "sequence": 1,
            "revision_index": None,
        }
    ]
    assert set(trace[0]) == {
        "tool",
        "outcome",
        "tool_use_id",
        "sequence",
        "revision_index",
    }


def test_budget_summary_dispatch_passes_only_server_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[object, BudgetResult, date, SpendingSource]] = []

    def fake_execute(
        arguments: object,
        budget_value: BudgetResult,
        period: date,
        *,
        spending_source: SpendingSource,
    ) -> dict[str, object]:
        recorded.append((arguments, budget_value, period, spending_source))
        return execute_budget_summary(
            arguments, budget_value, period, spending_source=spending_source
        )

    monkeypatch.setattr("app.agent.chat_dispatch.execute_budget_summary", fake_execute)
    funds = budget()
    call = ToolCall("sum-1", BUDGET_TOOL_NAME, {})
    trace: list[dict[str, object]] = []
    payload, _block = dispatch(call, funds, PERIOD, 99, "manual", trace)
    assert recorded == [({}, funds, PERIOD, "manual")]
    assert payload is not None
    assert payload["spending_source"] == "manual"


def test_budget_summary_rejects_overrides_without_sentinel() -> None:
    args: dict[str, object] = {
        "identity": _SECRET,
        "source": "manual",
        "cap": 1,
        "transactions": [_SECRET],
        "user_id": 9,
    }

    def record(_payload: dict[str, object]) -> str:
        return _REV

    call = ToolCall("sum-bad", BUDGET_TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    payload, block = dispatch(
        call, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    assert payload is None
    assert block == {
        "toolResult": {
            "toolUseId": "sum-bad",
            "content": [{"json": {"error": "arguments are invalid"}}],
            "status": "error",
        }
    }
    assert trace == [_error_trace(BUDGET_TOOL_NAME, "sum-bad", revision_index=None)]
    dumped = json.dumps({"block": block, "trace": trace})
    assert _SECRET not in dumped
    assert "BudgetToolError" not in dumped
    assert "identity" not in dumped


def test_budget_summary_then_planner_revision_index_skips_summary() -> None:
    summary = ToolCall("sum-1", BUDGET_TOOL_NAME, {})
    planner = ToolCall("plan-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []

    def record(_payload: dict[str, object]) -> str:
        return _REV

    summary_payload, _summary_block = dispatch(
        summary, budget(), PERIOD, 1, "fixture", trace
    )
    plan_payload, _plan_block = dispatch(
        planner, budget(), PERIOD, 1, "fixture", trace, record_evidence=record
    )
    expected_plan = execute_plan(arguments(), budget(), PERIOD)
    assert summary_payload is not None
    assert "evidence_id" not in summary_payload
    assert plan_payload is not None
    assert plan_payload["evidence_id"] == expected_plan["evidence_id"]
    assert trace[0]["tool"] == BUDGET_TOOL_NAME
    assert trace[0]["revision_index"] is None
    assert trace[1]["tool"] == TOOL_NAME
    assert trace[1]["revision_index"] == 1
    assert trace[1]["sequence"] == 2
    assert trace[1]["evidence_revision_id"] == _REV
