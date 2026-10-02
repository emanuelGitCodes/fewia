import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from app.evaluation_tool_score import score_tools

_METRICS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)


def _arguments(**changes: object) -> dict[str, object]:
    return {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "budget_period": "2026-09-01",
        **changes,
    }


def _case(tools: list[object] | None = None) -> dict[str, object]:
    return {
        "id": "test",
        "messages": [{"role": "user", "content": "Plan bean tacos."}],
        "expected": {
            "model_tools": (
                [{"name": "plan_groceries", "arguments": _arguments()}]
                if tools is None
                else tools
            ),
            "unnecessary_model_tools": [],
        },
    }


def _turn(calls: list[object]) -> dict[str, object]:
    return {
        "status": "completed",
        "result": {"reply": "Estimated plan.", "trace": []},
        "calls": calls,
    }


def _observation(calls: list[object] | None = None) -> dict[str, object]:
    return {
        "case_id": "test",
        "condition": "tool_enabled",
        "status": "completed",
        "turns": [
            _turn(
                [{"tool": "plan_groceries", "input": _arguments()}]
                if calls is None
                else calls
            )
        ],
    }


def _metric(score: dict[str, object], name: str) -> dict[str, object]:
    return cast(dict[str, object], score[name])


def _corpus_case(case_id: str) -> dict[str, object]:
    corpus = json.loads(
        (Path(__file__).parent / "evaluation" / "scenarios.json").read_text()
    )
    return next(
        cast(dict[str, object], case)
        for case in corpus["scenarios"]
        if case["id"] == case_id
    )


def test_success_and_schema_defaults() -> None:
    case = _case()
    expected = cast(dict[str, object], case["expected"])
    tools = cast(list[dict[str, object]], expected["model_tools"])
    tools[0]["arguments"] = _arguments(
        diet="omnivore",
        plan_cap_cents=None,
        pantry_ingredients=[],
        ingredient_exclusions=[],
    )
    score = score_tools(case, _observation())
    assert score["status"] == "passed"
    assert _metric(score, "valid_calls") == {
        "status": "passed",
        "numerator": 1,
        "denominator": 1,
    }
    assert _metric(score, "unnecessary_calls")["numerator"] == 0


def test_follow_up_checks_final_turn_only() -> None:
    case = _case()
    case["messages"] = [
        {"role": "user", "content": "Plan tacos."},
        {"role": "assistant", "content": "A plan."},
        {"role": "user", "content": "Revise the plan."},
    ]
    observation = _observation()
    observation["turns"] = [
        _turn([{"tool": "get_budget_summary", "input": {}}]),
        _turn([{"tool": "plan_groceries", "input": _arguments()}]),
    ]
    score = score_tools(case, observation)
    assert score["status"] == "passed"
    assert _metric(score, "valid_calls")["denominator"] == 2
    assert _metric(score, "expected_tool_selection")["denominator"] == 1
    assert _metric(score, "unnecessary_calls")["denominator"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"meals": [{"recipe_id": "chicken_tacos", "servings": 2}]},
        {"meals": [{"recipe_id": "bean_tacos", "servings": 3}]},
        {"plan_cap_cents": 101},
    ],
)
def test_wrong_arguments(changes: dict[str, object]) -> None:
    case = _case(
        [{"name": "plan_groceries", "arguments": _arguments(plan_cap_cents=100)}]
    )
    observation = _observation(
        [{"tool": "plan_groceries", "input": _arguments(plan_cap_cents=100) | changes}]
    )
    score = score_tools(case, observation)
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls")["status"] == "passed"
    assert _metric(score, "expected_arguments")["numerator"] == 0


@pytest.mark.parametrize(
    "call",
    [
        {"tool": "invented", "input": {}},
        {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=True)},
        {"tool": "plan_groceries", "input": _arguments(plan_cap_cents="100")},
        {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=100.0)},
        {"tool": "plan_groceries", "input": _arguments(extra=1)},
        {
            "tool": "plan_groceries",
            "input": _arguments(meals=[{"recipe_id": "bean_tacos", "servings": True}]),
        },
        {"tool": "plan_groceries", "input": "{}"},
        {"tool": "get_budget_summary", "input": {"user_id": 1}},
        {"tool": "get_budget_summary", "input": []},
        {"tool": "get_budget_summary", "input": None},
        {"tool": "get_budget_summary"},
        {"tool": "get_budget_summary", "input": {}, "extra": 1},
        {"tool": False, "input": {}},
        None,
    ],
)
def test_invalid_calls(call: object) -> None:
    score = score_tools(_case(), _observation([call]))
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls") == {
        "status": "failed",
        "numerator": 0,
        "denominator": 1,
    }


def test_budget_call_requires_empty_input() -> None:
    score = score_tools(
        _case([{"name": "get_budget_summary", "arguments": {}}]),
        _observation([{"tool": "get_budget_summary", "input": {}}]),
    )
    assert score["status"] == "passed"


def test_duplicate_calls_count_as_excess() -> None:
    call = {"tool": "plan_groceries", "input": _arguments()}
    score = score_tools(_case(), _observation([call, deepcopy(call)]))
    assert score["status"] == "failed"
    assert _metric(score, "unnecessary_calls") == {
        "status": "failed",
        "numerator": 1,
        "denominator": 2,
    }


def test_repeated_names_match_arguments_without_order_dependence() -> None:
    case = _case(
        [
            {"name": "plan_groceries", "arguments": _arguments(plan_cap_cents=100)},
            {"name": "plan_groceries", "arguments": _arguments(plan_cap_cents=200)},
        ]
    )
    observation = _observation(
        [
            {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=200)},
            {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=100)},
        ]
    )
    assert score_tools(case, observation)["status"] == "passed"


def test_forbidden_call_is_unnecessary() -> None:
    case = _case([])
    cast(dict[str, object], case["expected"])["unnecessary_model_tools"] = [
        "get_budget_summary"
    ]
    score = score_tools(
        case, _observation([{"tool": "get_budget_summary", "input": {}}])
    )
    assert score["status"] == "failed"
    assert _metric(score, "unnecessary_calls")["numerator"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"turns": None},
        {"turns": []},
        {"turns": {}},
        {"turns": [None]},
        {"turns": [{"status": "completed", "result": {"reply": "OK"}}]},
        {"turns": [{"status": "completed", "calls": []}]},
        {"turns": [{"status": "completed", "calls": [], "result": {}}]},
        {"turns": [{"status": "failed", "calls": [], "result": {"reply": "OK"}}]},
        {"turns": [_turn([]), _turn([])]},
        {"status": "failed"},
        {"status": None},
        {"case_id": "other"},
        {"case_id": None},
        {"condition": "unknown"},
    ],
)
def test_incomplete_evidence_never_passes_empty_expectations(
    changes: dict[str, object],
) -> None:
    score = score_tools(_case([]), _observation([]) | changes)
    assert score["status"] in {"failed", "unassessed"}
    for name in _METRICS:
        assert _metric(score, name)["status"] != "passed"


def test_missing_final_follow_up_never_passes() -> None:
    case = _case([])
    case["messages"] = [{"role": "user"}, {"role": "user"}]
    assert score_tools(case, _observation([]))["status"] != "passed"


def test_invalid_setup_call_fails_even_with_correct_final_call() -> None:
    case = _case()
    case["messages"] = [{"role": "user"}, {"role": "user"}]
    observation = _observation()
    turns = cast(list[object], observation["turns"])
    turns.insert(0, _turn([{"tool": "invented", "input": {}}]))
    score = score_tools(case, observation)
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls")["numerator"] == 1
    assert _metric(score, "valid_calls")["denominator"] == 2
    assert _metric(score, "unnecessary_calls")["numerator"] == 0


@pytest.mark.parametrize("condition", ["no_tool", "deterministic"])
def test_baseline_metrics_are_not_applicable(condition: str) -> None:
    score = score_tools(_case(), _observation([]) | {"condition": condition})
    assert score["status"] != "passed"
    for name in _METRICS:
        assert _metric(score, name) == {"status": "not_applicable"}


@pytest.mark.parametrize("condition", ["no_tool", "deterministic"])
def test_baselines_still_validate_observations(condition: str) -> None:
    observation = _observation([None]) | {"condition": condition}
    assert score_tools(_case(), observation)["status"] == "failed"
    observation = _observation([]) | {"condition": condition, "case_id": "wrong"}
    assert score_tools(_case(), observation)["status"] == "failed"


def test_clarification_without_calls_passes() -> None:
    case = _corpus_case("X02")
    observation = _observation([]) | {"case_id": case["id"]}
    score = score_tools(case, observation)
    assert score["status"] == "passed"
    assert _metric(score, "valid_calls")["denominator"] == 0


def test_expected_poison_cannot_create_observed_calls() -> None:
    observation = _observation([])
    before = deepcopy(observation)
    score = score_tools(
        _case([{"name": "invented", "arguments": {"execute": True}}]), observation
    )
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls")["denominator"] == 0
    assert _metric(score, "expected_tool_selection")["numerator"] == 0
    assert observation == before


@pytest.mark.parametrize("tools", [None, {}, [None], [{"name": "plan_groceries"}]])
def test_missing_gold_is_unassessed(tools: object) -> None:
    case = _case()
    cast(dict[str, object], case["expected"])["model_tools"] = tools
    assert score_tools(case, _observation())["status"] == "unassessed"


def test_strict_expected_scalar_types() -> None:
    case = _case(
        [{"name": "plan_groceries", "arguments": _arguments(plan_cap_cents=True)}]
    )
    observation = _observation(
        [{"tool": "plan_groceries", "input": _arguments(plan_cap_cents=1)}]
    )
    score = score_tools(case, observation)
    assert score["status"] == "failed"
    assert _metric(score, "expected_arguments")["numerator"] == 0


def test_scorer_does_not_execute_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("Scoring executed a tool")

    monkeypatch.setattr("app.agent.planning_tool.execute_plan", forbidden)
    monkeypatch.setattr("app.agent.budget_tool.execute_budget_summary", forbidden)
    case = _case()
    observation = _observation()
    before = deepcopy((case, observation))
    assert score_tools(case, observation)["status"] == "passed"
    assert (case, observation) == before
