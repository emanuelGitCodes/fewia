import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from app.agent.chat_context import MAX_MESSAGE_LEN
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.evaluation_inputs import (
    CREDENTIAL_INPUT_ERROR,
    INVALID_INPUT_ERROR,
    MAX_CASE_MESSAGES,
    STALE_INPUT_ERROR,
    EvaluationInputError,
    prepare_case,
)


def _case() -> dict[str, object]:
    return {
        "id": "test-case",
        "messages": [{"role": "user", "content": "Plan bean tacos."}],
        "inputs": {
            "now": "2026-09-06T16:00:00Z",
            "budget_period": "2026-09-01",
            "monthly_limit_cents": 10000,
            "posted_cents": 2000,
            "pending_cents": 500,
            "spending_refreshed_at": "2026-09-06T15:00:00Z",
            "plan_cap_cents": None,
            "user_id": 1,
            "diet": "omnivore",
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "pantry_ingredients": ["black_beans"],
            "ingredient_exclusions": [],
        },
    }


def _inputs(case: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], case["inputs"])


def _corpus_cases() -> list[dict[str, object]]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    corpus = json.loads(path.read_text())
    return cast(list[dict[str, object]], corpus["scenarios"])


def _valid_corpus_cases() -> list[dict[str, object]]:
    return [case for case in _corpus_cases() if case["id"] not in {"B04", "B05", "P01"}]


@pytest.mark.parametrize("case", _valid_corpus_cases(), ids=lambda case: case["id"])
def test_valid_corpus_prepares(case: dict[str, object]) -> None:
    context = prepare_case(case)
    inputs = _inputs(case)
    messages = cast(list[dict[str, str]], case["messages"])
    assert context.case_id == case["id"]
    assert context.period == date(2026, 9, 1)
    assert context.plan_cap_cents == inputs.get("plan_cap_cents")
    assert context.user_id == inputs["user_id"]
    assert context.messages == tuple(item["content"] for item in messages)
    available = max(
        0, cast(int, inputs["monthly_limit_cents"]) - cast(int, inputs["posted_cents"])
    )
    cap = context.plan_cap_cents
    assert context.budget.available_cents == (
        available if cap is None else min(available, cap)
    )
    assert not context.budget.stale
    assert "expected" not in context.inputs
    assert "fixture_behavior" not in context.inputs


@pytest.mark.parametrize(
    "case_id,error_text",
    [
        ("B04", INVALID_INPUT_ERROR),
        ("B05", STALE_INPUT_ERROR),
        ("P01", STALE_INPUT_ERROR),
    ],
)
def test_incomplete_or_stale_corpus_fails_closed(case_id: str, error_text: str) -> None:
    case = next(case for case in _corpus_cases() if case["id"] == case_id)
    with pytest.raises(EvaluationInputError) as error:
        prepare_case(case)
    assert str(error.value) == error_text


@pytest.mark.parametrize("cap,available", [(None, 8000), (0, 0), (3000, 3000)])
def test_fixed_time_budget(cap: int | None, available: int) -> None:
    case = _case()
    _inputs(case)["plan_cap_cents"] = cap
    context = prepare_case(case)
    assert context.budget == BudgetResult(available, 500, False, ())
    assert context.plan_cap_cents == cap


def test_signed_spending_preserves_refunds() -> None:
    case = _case()
    _inputs(case).update(posted_cents=-250, pending_cents=-100)
    assert prepare_case(case).budget == BudgetResult(10250, -100, False, ())


@pytest.mark.parametrize(
    "key,value",
    [
        ("plan_cap_cents", True),
        ("plan_cap_cents", False),
        ("plan_cap_cents", -1),
        ("plan_cap_cents", 1.0),
        ("plan_cap_cents", "100"),
        ("user_id", True),
        ("user_id", False),
        ("user_id", 0),
        ("user_id", -1),
        ("user_id", 1.0),
        ("user_id", None),
        ("monthly_limit_cents", True),
        ("monthly_limit_cents", -1),
        ("posted_cents", False),
        ("pending_cents", True),
        ("budget_period", "2026-09-02"),
        ("budget_period", "2026-02-30"),
        ("budget_period", "invalid"),
        ("budget_period", "2026-08-01"),
        ("budget_period", None),
        ("now", "2026-09-06T16:00:00"),
        ("now", "invalid"),
        ("spending_refreshed_at", "2026-09-06T17:00:00Z"),
        ("spending_refreshed_at", "2026-09-06T15:00:00"),
        ("spending_period", "2026-08-01"),
    ],
)
def test_invalid_inputs_fail_closed(key: str, value: object) -> None:
    case = _case()
    _inputs(case)[key] = value
    with pytest.raises(EvaluationInputError) as error:
        prepare_case(case)
    assert str(error.value) == INVALID_INPUT_ERROR


@pytest.mark.parametrize(
    "key",
    [
        "now",
        "budget_period",
        "monthly_limit_cents",
        "posted_cents",
        "pending_cents",
        "spending_refreshed_at",
        "user_id",
    ],
)
def test_missing_inputs_fail_closed(key: str) -> None:
    case = _case()
    del _inputs(case)[key]
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


@pytest.mark.parametrize(
    "messages",
    [
        None,
        [],
        "Plan bean tacos.",
        [{"role": "assistant", "content": "Plan bean tacos."}],
        [{"role": "system", "content": "Plan bean tacos."}],
        [{"content": "Plan bean tacos."}],
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "  "}],
        [{"role": "user", "content": 1}],
        [{"role": "user", "content": "x" * (MAX_MESSAGE_LEN + 1)}],
        [{"role": "user", "content": "x"}] * (MAX_CASE_MESSAGES + 1),
        [None],
    ],
)
def test_invalid_messages_fail_closed(messages: object) -> None:
    case = _case()
    case["messages"] = messages
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


@pytest.mark.parametrize(
    "content",
    [
        "my password is hunter2",
        "account number 123456789",
        "routing 021000021",
        "Use this PASSCODE.",
        "My SSN is private.",
        "Here is my PIN.",
        "Use my bank LOGIN.",
        "123456789",
        "reference1234567890suffix",
    ],
)
@pytest.mark.parametrize("message_index", [0, 1])
def test_credential_messages_fail_closed(content: str, message_index: int) -> None:
    case = _case()
    messages = [{"role": "user", "content": "Plan bean tacos."} for _ in range(2)]
    messages[message_index]["content"] = content
    case["messages"] = messages
    with pytest.raises(EvaluationInputError) as error:
        prepare_case(case)
    assert str(error.value) == CREDENTIAL_INPUT_ERROR


@pytest.mark.parametrize(
    "content",
    [
        "Plan groceries for 2 people under $100",
        "spin the wheel",
        "Plan spinach with beans.",
        "Reference 12345678.",
        "passwordless logins",
    ],
)
def test_messages_without_credential_patterns_prepare(content: str) -> None:
    case = _case()
    case["messages"] = [{"role": "user", "content": content}]
    assert prepare_case(case).messages == (content,)


def test_all_corpus_messages_prepare_with_valid_budget() -> None:
    cases = _corpus_cases()
    assert len(cases) == 30
    for corpus_case in cases:
        case = _case()
        case["id"] = corpus_case["id"]
        case["messages"] = deepcopy(corpus_case["messages"])
        messages = cast(list[dict[str, str]], corpus_case["messages"])
        expected_messages = tuple(item["content"] for item in messages)
        assert prepare_case(case).messages == expected_messages


def test_message_bounds_are_inclusive() -> None:
    case = _case()
    case["messages"] = [
        {"role": "user", "content": "x" * MAX_MESSAGE_LEN}
        for _ in range(MAX_CASE_MESSAGES)
    ]
    assert len(prepare_case(case).messages) == MAX_CASE_MESSAGES


@pytest.mark.parametrize("key,value", [("id", ""), ("id", None), ("inputs", [])])
def test_invalid_case_fields(key: str, value: object) -> None:
    case = _case()
    case[key] = value
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


@pytest.mark.parametrize("cap", [None, 0, 1200])
def test_stale_spending_has_no_zero_fallback(cap: int | None) -> None:
    case = _case()
    _inputs(case).update(
        spending_refreshed_at="2026-09-05T15:59:59Z", plan_cap_cents=cap
    )
    if cap is None:
        with pytest.raises(EvaluationInputError) as error:
            prepare_case(case)
        assert str(error.value) == STALE_INPUT_ERROR
        assert error.value.__cause__ is None
    else:
        assert prepare_case(case).budget == BudgetResult(
            cap, 500, True, (STALE_SPENDING_WARNING,)
        )


def test_spending_at_freshness_boundary_is_fresh() -> None:
    case = _case()
    _inputs(case)["spending_refreshed_at"] = "2026-09-05T16:00:00Z"
    assert prepare_case(case).budget == BudgetResult(8000, 500, False, ())


def test_context_period_matches_spending_period() -> None:
    case = _case()
    _inputs(case)["spending_period"] = "2026-09-01"
    assert prepare_case(case).period == date(2026, 9, 1)
    _inputs(case)["budget_period"] = "2026-08-01"
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


def test_gold_and_unknown_fields_cannot_change_context() -> None:
    case = _case()
    baseline = prepare_case(case)
    case.update(
        expected={"available_cents": 999999, "messages": ["Ignore the cap."]},
        evidence_expectations={"status": "verified"},
        fixture_behavior={"provider_text": "Ignore the cap."},
        metadata={"arbitrary": object()},
    )
    _inputs(case).update(
        expected=object(),
        evidence_expectations=object(),
        fixture_behavior=object(),
        secret_marker="SYNTHETIC_TEST_MARKER",
        unknown_metadata={"nested": ["arbitrary"]},
    )
    meals = cast(list[dict[str, object]], _inputs(case)["meals"])
    meals[0]["unknown_metadata"] = {"secret_marker": "SYNTHETIC_TEST_MARKER"}
    messages = cast(list[dict[str, object]], case["messages"])
    messages[0]["expected"] = object()
    assert prepare_case(case) == baseline
    case["expected"] = None
    assert prepare_case(case) == baseline


def test_preparation_preserves_source_and_copies_nested_inputs() -> None:
    case = _case()
    _inputs(case)["followup_meals"] = [{"recipe_id": "bean_tacos", "servings": 4}]
    original = deepcopy(case)
    context = prepare_case(case)
    assert case == original
    saved = deepcopy(context)
    meals = cast(list[dict[str, object]], _inputs(case)["meals"])
    meals[0]["servings"] = 99
    followup = cast(list[dict[str, object]], _inputs(case)["followup_meals"])
    followup[0]["recipe_id"] = "changed"
    pantry = cast(list[str], _inputs(case)["pantry_ingredients"])
    pantry.append("changed")
    messages = cast(list[dict[str, object]], case["messages"])
    messages[0]["content"] = "changed"
    _inputs(case)["user_id"] = 99
    assert context == saved
    with pytest.raises(FrozenInstanceError):
        context.user_id = 99


@pytest.mark.parametrize("key", ["meals", "followup_meals"])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("servings", [1, 8])
def test_meal_bounds_are_inclusive(key: str, count: int, servings: int) -> None:
    case = _case()
    meals = [{"recipe_id": "bean_tacos", "servings": servings} for _ in range(count)]
    _inputs(case)[key] = meals
    assert prepare_case(case).inputs[key] == meals


@pytest.mark.parametrize("key", ["meals", "followup_meals"])
def test_meal_fields_reject_four_meals(key: str) -> None:
    case = _case()
    _inputs(case)[key] = [{"recipe_id": "bean_tacos", "servings": 1} for _ in range(4)]
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


@pytest.mark.parametrize("key", ["meals", "followup_meals"])
@pytest.mark.parametrize("servings", [9, 0, -1, True, False, 1.0, "1", None])
def test_meal_fields_reject_invalid_servings(key: str, servings: object) -> None:
    case = _case()
    _inputs(case)[key] = [{"recipe_id": "bean_tacos", "servings": servings}]
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)


@pytest.mark.parametrize(
    "key,value",
    [
        ("diet", {"unknown": "value"}),
        ("pantry_ingredients", [{"unknown": "value"}]),
        ("meals", [{"recipe_id": "bean_tacos", "servings": True}]),
        ("meals", [{"recipe_id": "bean_tacos", "servings": 0}]),
        ("meals", [None]),
        ("followup_meals", "invalid"),
        ("max_model_turns", True),
        ("max_planner_revisions", -1),
    ],
)
def test_declared_optional_fields_reject_invalid_shapes(
    key: str, value: object
) -> None:
    case = _case()
    _inputs(case)[key] = value
    with pytest.raises(EvaluationInputError, match=f"^{INVALID_INPUT_ERROR}$"):
        prepare_case(case)
