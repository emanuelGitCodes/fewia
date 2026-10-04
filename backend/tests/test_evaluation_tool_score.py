import json
from copy import deepcopy
from datetime import date
from itertools import permutations
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


def _chicken_tacos_call(servings: int) -> dict[str, object]:
    return {
        "tool": "plan_groceries",
        "input": _arguments(
            meals=[{"recipe_id": "chicken_tacos", "servings": servings}],
            diet="omnivore",
            pantry_ingredients=[],
            ingredient_exclusions=[],
        ),
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


def _result(**changes: object) -> dict[str, object]:
    return {
        "status": "planned",
        "answer": "Estimated plan.",
        "request": _arguments(
            diet="omnivore",
            plan_cap_cents=None,
            pantry_ingredients=[],
            ingredient_exclusions=[],
        ),
        "plan": {"accepted": True, "total_cents": 200},
        "budget": {
            "available_cents": 1000,
            "pending_cents": 0,
            "stale": False,
            "warnings": [],
        },
        **changes,
    }


def _turn(calls: list[object], **changes: object) -> dict[str, object]:
    return {
        "status": "completed",
        "result": _result(),
        "calls": calls,
        **changes,
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
    assert _metric(score, "expected_arguments")["numerator"] == 0


@pytest.mark.parametrize(
    "period",
    [1788220800, 1788220800.0, True, date(2026, 9, 1), "20260901", "2026-9-1"],
    ids=["timestamp", "float_timestamp", "bool", "date", "compact", "unpadded"],
)
def test_invalid_budget_period_calls(period: object) -> None:
    score = score_tools(
        _case(),
        _observation(
            [{"tool": "plan_groceries", "input": _arguments(budget_period=period)}]
        ),
    )
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
    assert _metric(score, "expected_tool_selection")["numerator"] == 1
    assert _metric(score, "expected_arguments")["numerator"] == 1
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


@pytest.mark.parametrize(
    ("expected_servings", "selected", "excess"),
    [((1,), 1, 1), ((1, 2), 2, 0), ((2, 1), 2, 0)],
)
@pytest.mark.parametrize("observed_servings", [(3, 1), (1, 3)])
def test_wrong_arguments_do_not_consume_later_matches(
    expected_servings: tuple[int, ...],
    selected: int,
    excess: int,
    observed_servings: tuple[int, int],
) -> None:
    case = _case(
        [
            {
                "name": "plan_groceries",
                "arguments": _arguments(
                    meals=[{"recipe_id": "bean_tacos", "servings": servings}]
                ),
            }
            for servings in expected_servings
        ]
    )
    observation = _observation(
        [
            {
                "tool": "plan_groceries",
                "input": _arguments(
                    meals=[{"recipe_id": "bean_tacos", "servings": servings}]
                ),
            }
            for servings in observed_servings
        ]
    )
    score = score_tools(case, observation)
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls") == {
        "status": "passed",
        "numerator": 2,
        "denominator": 2,
    }
    assert _metric(score, "expected_tool_selection") == {
        "status": "passed",
        "numerator": selected,
        "denominator": selected,
    }
    assert _metric(score, "expected_arguments")["numerator"] == 1
    assert _metric(score, "expected_arguments")["denominator"] == selected
    assert _metric(score, "unnecessary_calls")["numerator"] == excess
    assert _metric(score, "unnecessary_calls")["denominator"] == 2


@pytest.mark.parametrize("expected_order", list(permutations((0, 1, 2))))
@pytest.mark.parametrize("observed_order", list(permutations((0, 1, 2))))
def test_overlapping_expectations_allow_chained_reassignment(
    expected_order: tuple[int, int, int], observed_order: tuple[int, int, int]
) -> None:
    required = [
        {"budget_period": "2026-09-01"},
        {"meals": [{"recipe_id": "bean_tacos", "servings": 1}]},
        {"plan_cap_cents": 100},
    ]
    inputs = [
        _arguments(
            meals=[{"recipe_id": "bean_tacos", "servings": 1}], plan_cap_cents=100
        ),
        _arguments(
            meals=[{"recipe_id": "bean_tacos", "servings": 1}], plan_cap_cents=200
        ),
        _arguments(plan_cap_cents=200),
    ]
    case = _case(
        [
            {"name": "plan_groceries", "arguments": required[index]}
            for index in expected_order
        ]
    )
    observation = _observation(
        [{"tool": "plan_groceries", "input": inputs[index]} for index in observed_order]
    )
    before = deepcopy((case, observation))
    score = score_tools(case, observation)
    assert score["status"] == "passed"
    assert _metric(score, "expected_tool_selection") == {
        "status": "passed",
        "numerator": 3,
        "denominator": 3,
    }
    assert _metric(score, "expected_arguments") == {
        "status": "passed",
        "numerator": 3,
        "denominator": 3,
    }
    assert _metric(score, "unnecessary_calls")["numerator"] == 0
    assert (case, observation) == before


@pytest.mark.parametrize("flexible", [{}, {"budget_period": "2026-09-01"}])
@pytest.mark.parametrize("reverse_expected", [False, True])
@pytest.mark.parametrize("reverse_observed", [False, True])
def test_subset_expectation_does_not_take_only_specific_match(
    flexible: dict[str, object], reverse_expected: bool, reverse_observed: bool
) -> None:
    tools: list[object] = [
        {"name": "plan_groceries", "arguments": flexible},
        {"name": "plan_groceries", "arguments": _arguments(plan_cap_cents=100)},
    ]
    calls: list[object] = [
        {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=100)},
        {"tool": "plan_groceries", "input": _arguments(plan_cap_cents=200)},
    ]
    score = score_tools(
        _case(tools[::-1] if reverse_expected else tools),
        _observation(calls[::-1] if reverse_observed else calls),
    )
    assert score["status"] == "passed"
    assert _metric(score, "expected_tool_selection")["numerator"] == 2
    assert _metric(score, "expected_arguments")["numerator"] == 2
    assert _metric(score, "unnecessary_calls")["numerator"] == 0


@pytest.mark.parametrize("first_arguments", [{}, _arguments()])
def test_one_call_cannot_match_two_expectations(
    first_arguments: dict[str, object],
) -> None:
    score = score_tools(
        _case(
            [
                {"name": "plan_groceries", "arguments": first_arguments},
                {"name": "plan_groceries", "arguments": _arguments()},
            ]
        ),
        _observation(),
    )
    assert score["status"] == "failed"
    assert _metric(score, "expected_tool_selection") == {
        "status": "failed",
        "numerator": 1,
        "denominator": 2,
    }
    assert _metric(score, "expected_arguments") == {
        "status": "failed",
        "numerator": 1,
        "denominator": 2,
    }
    assert _metric(score, "unnecessary_calls")["numerator"] == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_invalid_call_does_not_consume_valid_argument_match(reverse: bool) -> None:
    calls: list[object] = [
        {
            "tool": "plan_groceries",
            "input": _arguments(meals=[{"recipe_id": "bean_tacos", "servings": True}]),
        },
        {"tool": "plan_groceries", "input": _arguments()},
    ]
    score = score_tools(_case(), _observation(calls[::-1] if reverse else calls))
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls") == {
        "status": "failed",
        "numerator": 1,
        "denominator": 2,
    }
    assert _metric(score, "expected_tool_selection")["numerator"] == 1
    assert _metric(score, "expected_arguments")["numerator"] == 1
    assert _metric(score, "unnecessary_calls")["numerator"] == 1


def test_forbidden_expectation_never_matches_valid_call() -> None:
    case = _case(
        [
            {"name": "plan_groceries", "arguments": _arguments()},
            {"name": "get_budget_summary", "arguments": {}},
        ]
    )
    cast(dict[str, object], case["expected"])["unnecessary_model_tools"] = [
        "plan_groceries"
    ]
    score = score_tools(
        case,
        _observation(
            [
                {"tool": "plan_groceries", "input": _arguments()},
                {"tool": "get_budget_summary", "input": {}},
            ]
        ),
    )
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls")["numerator"] == 2
    assert _metric(score, "expected_tool_selection")["numerator"] == 1
    assert _metric(score, "expected_tool_selection")["denominator"] == 2
    assert _metric(score, "expected_arguments")["numerator"] == 1
    assert _metric(score, "expected_arguments")["denominator"] == 2
    assert _metric(score, "unnecessary_calls")["numerator"] == 1


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
        {"turns": [{"status": "completed", "result": _result()}]},
        {"turns": [{"status": "completed", "calls": []}]},
        {"turns": [{"status": "completed", "calls": [], "result": {}}]},
        {"turns": [_turn([], status="failed")]},
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


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {},
        {"made_up": True},
        {"reply": "Estimated plan.", "trace": []},
        _result(status="completed"),
        _result(status=True),
        _result(answer=None),
        _result(answer=""),
        _result(answer="x" * 4097),
        _result(request=None),
        _result(plan=[]),
        _result(budget="1000"),
        _result(plan={"accepted": False}),
        _result(plan={"accepted": 1}),
        _result(status="needs_revision"),
        _result(status="clarification"),
        _result(status="limit"),
        _result(status="incomplete"),
    ],
)
def test_malformed_completed_result_never_passes_empty_expectations(
    result: object,
) -> None:
    observation = _observation([]) | {"turns": [_turn([], result=result)]}
    score = score_tools(_case([]), observation)
    assert score["status"] != "passed"
    assert cast(dict[str, object], score["checks"])["turns_complete"] is False
    for name in _METRICS:
        assert _metric(score, name)["status"] != "passed"


@pytest.mark.parametrize("field", ["status", "answer", "request", "plan", "budget"])
def test_missing_public_result_field_never_passes(field: str) -> None:
    result = _result()
    del result[field]
    observation = _observation([]) | {"turns": [_turn([], result=result)]}
    score = score_tools(_case([]), observation)
    assert score["status"] != "passed"
    assert cast(dict[str, object], score["checks"])["turns_complete"] is False


@pytest.mark.parametrize(
    "status", ["planned", "needs_revision", "clarification", "limit", "incomplete"]
)
def test_valid_public_results_pass_empty_expectations(status: str) -> None:
    result = _result(status=status)
    if status == "needs_revision":
        cast(dict[str, object], result["plan"])["accepted"] = False
    elif status in ("clarification", "limit", "incomplete"):
        result.update(request=None, plan=None, budget=None)
    observation = _observation([]) | {"turns": [_turn([], result=result)]}
    score = score_tools(_case([]), observation)
    assert score["status"] == "passed"
    assert cast(dict[str, object], score["checks"])["turns_complete"] is True


def test_malformed_setup_result_never_passes_valid_final_turn() -> None:
    case = _case([])
    case["messages"] = [{"role": "user"}, {"role": "user"}]
    observation = _observation([]) | {
        "turns": [_turn([], result={"made_up": True}), _turn([])]
    }
    score = score_tools(case, observation)
    assert score["status"] != "passed"
    assert cast(dict[str, object], score["checks"])["turns_complete"] is False
    for name in _METRICS:
        assert _metric(score, name)["status"] != "passed"


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


@pytest.mark.parametrize("condition", ["no_tool", "deterministic"])
def test_baseline_malformed_result_keeps_metrics_not_applicable(condition: str) -> None:
    observation = _observation([]) | {
        "condition": condition,
        "turns": [_turn([], result={"made_up": True})],
    }
    score = score_tools(_case([]), observation)
    assert score["status"] != "passed"
    assert cast(dict[str, object], score["checks"])["turns_complete"] is False
    for name in _METRICS:
        assert _metric(score, name) == {"status": "not_applicable"}


def test_clarification_without_calls_passes() -> None:
    case = _corpus_case("X02")
    result = _result(
        status="clarification",
        answer="Which recipe and servings do you want?",
        request=None,
        plan=None,
        budget=None,
    )
    observation = _observation([]) | {
        "case_id": case["id"],
        "turns": [_turn([], result=result)],
    }
    score = score_tools(case, observation)
    assert score["status"] == "passed"
    assert _metric(score, "valid_calls")["denominator"] == 0


@pytest.mark.parametrize(
    ("case_id", "turn_count", "expected_count"),
    [
        ("F01", 2, 1),
        ("F02", 3, 1),
        ("F04", 2, 0),
        ("F05", 2, 1),
        ("X04", 1, 1),
        ("A01", 1, 1),
        ("A02", 1, 1),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_original_corpus_tool_expectations(
    case_id: str, turn_count: int, expected_count: int, reverse: bool
) -> None:
    case = _corpus_case(case_id)
    tools = cast(
        list[dict[str, object]],
        cast(dict[str, object], case["expected"])["model_tools"],
    )
    calls: list[object] = [
        {"tool": tool["name"], "input": deepcopy(tool["arguments"])} for tool in tools
    ]
    observation = _observation([]) | {
        "case_id": case_id,
        "turns": [
            *[_turn([]) for _ in range(turn_count - 1)],
            _turn(calls[::-1] if reverse else calls),
        ],
    }
    score = score_tools(case, observation)
    assert score["status"] == "passed"
    assert _metric(score, "valid_calls")["numerator"] == expected_count
    for metric in ("expected_tool_selection", "expected_arguments"):
        assert _metric(score, metric) == {
            "status": "passed",
            "numerator": expected_count,
            "denominator": expected_count,
        }
    assert _metric(score, "unnecessary_calls")["numerator"] == 0


@pytest.mark.parametrize("unexpected_final_call", [False, True])
def test_f04_clarification_scores_only_final_calls(unexpected_final_call: bool) -> None:
    case = _corpus_case("F04")
    planner = {
        "tool": "plan_groceries",
        "input": _arguments(
            meals=[{"recipe_id": "breakfast_burritos", "servings": 2}],
            diet="vegetarian",
            pantry_ingredients=[],
            ingredient_exclusions=[],
        ),
    }
    clarification = _result(
        status="clarification",
        answer="Breakfast burritos contain eggs. Which vegan recipe do you want?",
        request=None,
        plan=None,
        budget=None,
    )
    observation = _observation([]) | {
        "case_id": "F04",
        "turns": [
            _turn([planner], result=_result(request=deepcopy(planner["input"]))),
            _turn(
                [deepcopy(planner)] if unexpected_final_call else [],
                result=clarification,
            ),
        ],
    }
    score = score_tools(case, observation)
    assert score["status"] == ("failed" if unexpected_final_call else "passed")
    assert _metric(score, "valid_calls") == {
        "status": "passed",
        "numerator": 2 if unexpected_final_call else 1,
        "denominator": 2 if unexpected_final_call else 1,
    }
    for metric in ("expected_tool_selection", "expected_arguments"):
        assert _metric(score, metric) == {
            "status": "passed",
            "numerator": 0,
            "denominator": 0,
        }
    assert _metric(score, "unnecessary_calls") == {
        "status": "failed" if unexpected_final_call else "passed",
        "numerator": 1 if unexpected_final_call else 0,
        "denominator": 1 if unexpected_final_call else 0,
    }


@pytest.mark.parametrize("duplicate_final_call", [False, True])
def test_f05_revision_scores_only_final_calls(duplicate_final_call: bool) -> None:
    case = _corpus_case("F05")
    setup, final = _chicken_tacos_call(2), _chicken_tacos_call(4)
    observation = _observation([]) | {
        "case_id": "F05",
        "turns": [
            _turn([setup], result=_result(request=deepcopy(setup["input"]))),
            _turn(
                [final, deepcopy(final)] if duplicate_final_call else [final],
                result=_result(request=deepcopy(final["input"])),
            ),
        ],
    }
    score = score_tools(case, observation)
    assert score["status"] == ("failed" if duplicate_final_call else "passed")
    assert _metric(score, "valid_calls") == {
        "status": "passed",
        "numerator": 3 if duplicate_final_call else 2,
        "denominator": 3 if duplicate_final_call else 2,
    }
    for metric in ("expected_tool_selection", "expected_arguments"):
        assert _metric(score, metric) == {
            "status": "passed",
            "numerator": 1,
            "denominator": 1,
        }
    assert _metric(score, "unnecessary_calls") == {
        "status": "failed" if duplicate_final_call else "passed",
        "numerator": 1 if duplicate_final_call else 0,
        "denominator": 2 if duplicate_final_call else 1,
    }


def test_original_corpus_setup_match_does_not_count_on_final_turn() -> None:
    case = _corpus_case("F05")
    setup, final = _chicken_tacos_call(4), _chicken_tacos_call(2)
    assert cast(dict[str, object], case["expected"])["model_tools"] == [
        {"name": "plan_groceries", "arguments": setup["input"]}
    ]
    observation = _observation([]) | {
        "case_id": "F05",
        "turns": [
            _turn([setup], result=_result(request=deepcopy(setup["input"]))),
            _turn([final], result=_result(request=deepcopy(final["input"]))),
        ],
    }
    score = score_tools(case, observation)
    assert score["status"] == "failed"
    assert _metric(score, "valid_calls") == {
        "status": "passed",
        "numerator": 2,
        "denominator": 2,
    }
    assert _metric(score, "expected_tool_selection") == {
        "status": "passed",
        "numerator": 1,
        "denominator": 1,
    }
    assert _metric(score, "expected_arguments") == {
        "status": "failed",
        "numerator": 0,
        "denominator": 1,
    }
    assert _metric(score, "unnecessary_calls") == {
        "status": "passed",
        "numerator": 0,
        "denominator": 1,
    }


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
