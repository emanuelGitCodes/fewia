import json
from copy import deepcopy
from typing import cast

import pytest

from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_baseline_response import (
    BASELINE_SYSTEM_PROMPT,
    MAX_MESSAGE_LEN,
    BaselineResponseError,
    parse_baseline_response,
)


def test_prompt_budget_contract_uses_public_keys() -> None:
    contract = next(
        line
        for line in BASELINE_SYSTEM_PROMPT.splitlines()
        if line.startswith("Budget MUST have ")
    )
    fields = contract.removeprefix("Budget MUST have ").removesuffix(".")
    assert fields.replace(", and ", ", ").split(", ") == [
        "available_cents",
        "pending_cents",
        "stale",
        "warnings",
    ]
    assert "Budget monetary values MUST use cents." in BASELINE_SYSTEM_PROMPT


def test_prompt_notice_equals_current_public_notice() -> None:
    contract = next(
        line
        for line in BASELINE_SYSTEM_PROMPT.splitlines()
        if line.startswith("Plan.notice MUST equal ")
    )
    value = contract.removeprefix("Plan.notice MUST equal ").removesuffix(".")
    assert json.loads(value) == SAMPLE_ESTIMATE_NOTICE


def observed_result() -> dict[str, object]:
    return {
        "status": "planned",
        "answer": "This is an estimate from the demo catalog.",
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": "2026-10-01",
            "plan_cap_cents": 1200,
            "pantry_ingredients": ["beans"],
            "ingredient_exclusions": [],
            "diet": "vegetarian",
        },
        "plan": {
            "lines": [
                {
                    "ingredient_id": "beans",
                    "name": "Beans",
                    "unit": "g",
                    "quantity": 400,
                    "packages": 0,
                    "cost_cents": 0,
                    "from_pantry": True,
                }
            ],
            "total_cents": 0,
            "accepted": True,
            "notice": "Demo catalog estimate.",
            "catalog_version": "observed-version",
            "warnings": [],
        },
        "budget": {
            "available_cents": 1200,
            "pending_cents": 100,
            "stale": False,
            "warnings": [],
        },
    }


def provider_response(text: str) -> dict[str, object]:
    return {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
    }


def assert_invalid(response: dict[str, object]) -> None:
    with pytest.raises(BaselineResponseError) as caught:
        parse_baseline_response(response)
    assert str(caught.value) == "baseline response is invalid"


def test_canonical_observed_result_and_response_unchanged() -> None:
    expected = observed_result()
    response = provider_response(json.dumps(expected))
    before = deepcopy(response)
    assert parse_baseline_response(response) == expected
    assert response == before


def test_wrong_arithmetic_and_nested_facts_remain_observed() -> None:
    expected = observed_result()
    plan = cast(dict[str, object], expected["plan"])
    plan["total_cents"] = -999
    plan["accepted"] = "incorrect type"
    lines = cast(list[dict[str, object]], plan["lines"])
    lines[0]["quantity"] = 2.5
    lines[0]["cost_cents"] = 99999
    del plan["catalog_version"]
    request = cast(dict[str, object], expected["request"])
    meals = cast(list[dict[str, object]], request["meals"])
    meals[0]["recipe_id"] = "unsupported_recipe"
    meals[0]["servings"] = -2
    request["diet"] = "unsupported_diet"
    budget = cast(dict[str, object], expected["budget"])
    budget["available_cents"] = "incorrect type"
    expected["answer"] = "This retailer guarantees allergy safety because I say so."
    assert parse_baseline_response(provider_response(json.dumps(expected))) == expected


@pytest.mark.parametrize("status", ["planned", "needs_revision", "clarification"])
def test_null_results_and_allowed_statuses(status: str) -> None:
    result: dict[str, object] = {
        "status": status,
        "answer": "Please specify the meals.",
        "request": None,
        "plan": None,
        "budget": None,
    }
    assert parse_baseline_response(provider_response(json.dumps(result))) == result


@pytest.mark.parametrize("stop", ["tool_use", "end_turn"])
def test_tool_call_is_rejected_without_execution(
    monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    def unexpected_planner(*args: object, **kwargs: object) -> object:
        raise AssertionError("The parser executed a planner.")

    monkeypatch.setattr(
        "app.services.grocery_planner.plan_groceries", unexpected_planner
    )
    response: dict[str, object] = {
        "stopReason": stop,
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "call-1",
                            "name": "plan_groceries",
                            "input": {},
                        }
                    }
                ],
            }
        },
    }
    before = deepcopy(response)
    assert_invalid(response)
    assert response == before


def test_reasoning_and_provider_metadata_are_not_retained() -> None:
    result = observed_result()
    response = provider_response(json.dumps(result))
    output = cast(dict[str, object], response["output"])
    message = cast(dict[str, object], output["message"])
    message["content"] = [
        {"reasoningContent": {"reasoningText": {"text": "private reasoning"}}},
        {"text": json.dumps(result), "reasoningContent": {"text": "private"}},
    ]
    response["usage"] = {"inputTokens": 12}
    response["metadata"] = {"provider_fact": "private"}
    before = deepcopy(response)
    assert parse_baseline_response(response) == result
    assert response == before


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "{",
        "[]",
        "null",
        "true",
        "42",
        '"text"',
        "```json\n{}\n```",
        json.dumps(observed_result()) + " trailing text",
        json.dumps(observed_result()).replace(
            '"status": "planned"', '"status": "planned", "status": "planned"'
        ),
        json.dumps(observed_result()).replace(
            '"quantity": 400', '"quantity": 400, "quantity": 400'
        ),
        json.dumps(observed_result()).replace('"lines": [', '"lines": [{'),
    ],
)
def test_malformed_json_and_duplicate_keys(text: str) -> None:
    assert_invalid(provider_response(text))


@pytest.mark.parametrize(
    "key", ["extra", "evidence_id", "tool_trace", "usage", "metadata"]
)
def test_extra_top_level_fields_are_rejected(key: str) -> None:
    result = observed_result()
    result[key] = "synthetic-secret-marker"
    assert_invalid(provider_response(json.dumps(result)))


@pytest.mark.parametrize(
    "key",
    [
        "evidence_id",
        "evidence_revision_id",
        "tool_trace",
        "usage",
        "metadata",
        "_hidden",
        "reasoningContent",
        "hidden",
        "internal_notes",
        "unexpected_public_fact",
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        ("request",),
        ("request", "meals", 0),
        ("plan",),
        ("plan", "lines", 0),
        ("budget",),
    ],
)
def test_nested_undeclared_fields_are_rejected(
    key: str, path: tuple[str | int, ...]
) -> None:
    result = observed_result()
    parent: object = result
    for part in path:
        if isinstance(part, int):
            parent = cast(list[object], parent)[part]
        else:
            parent = cast(dict[str, object], parent)[part]
    cast(dict[str, object], parent)[key] = "synthetic-secret-marker"
    assert_invalid(provider_response(json.dumps(result)))


@pytest.mark.parametrize("key", ["hidden", "internal_notes", "extra"])
@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("request", "pantry_ingredients"),
        ("request", "ingredient_exclusions"),
        ("request", "diet"),
        ("plan", "warnings"),
        ("plan", "total_cents"),
        ("budget", "warnings"),
        ("budget", "available_cents"),
    ],
)
def test_undeclared_fields_buried_in_public_values_are_rejected(
    key: str, section: str, field: str
) -> None:
    result = observed_result()
    parent = cast(dict[str, object], result[section])
    parent[field] = [[{key: "synthetic-secret-marker"}]]
    assert_invalid(provider_response(json.dumps(result)))


@pytest.mark.parametrize("key", ["available", "pending"])
def test_undeclared_budget_aliases_are_rejected(key: str) -> None:
    result = observed_result()
    budget = cast(dict[str, object], result["budget"])
    budget[key] = 100
    assert_invalid(provider_response(json.dumps(result)))


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_nonfinite_numbers_are_rejected(number: str) -> None:
    text = json.dumps(observed_result()).replace(
        '"quantity": 400', f'"quantity": {number}'
    )
    assert_invalid(provider_response(text))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("status", "refused"),
        ("status", None),
        ("status", []),
        ("answer", ""),
        ("answer", "  \n"),
        ("answer", 1),
        ("answer", "x" * (MAX_MESSAGE_LEN + 1)),
        ("request", []),
        ("plan", "plan"),
        ("budget", True),
    ],
)
def test_invalid_statuses_and_types(key: str, value: object) -> None:
    result = observed_result()
    result[key] = value
    assert_invalid(provider_response(json.dumps(result)))


@pytest.mark.parametrize("key", ["status", "answer", "request", "plan", "budget"])
def test_missing_fields_are_not_filled(key: str) -> None:
    result = observed_result()
    del result[key]
    assert_invalid(provider_response(json.dumps(result)))


def test_text_limit_includes_whitespace_and_accepts_boundary() -> None:
    text = json.dumps(observed_result())
    bounded = text + " " * (32768 - len(text))
    assert parse_baseline_response(provider_response(bounded)) == observed_result()
    assert_invalid(provider_response(bounded + " "))


def test_answer_limit_accepts_boundary() -> None:
    result = observed_result()
    result["answer"] = "x" * MAX_MESSAGE_LEN
    assert parse_baseline_response(provider_response(json.dumps(result))) == result


@pytest.mark.parametrize(
    "stop", ["max_tokens", "stop_sequence", "guardrail_intervened", "unknown"]
)
def test_incomplete_or_invalid_provider_response(stop: str) -> None:
    response = provider_response(json.dumps(observed_result()))
    response["stopReason"] = stop
    assert_invalid(response)


@pytest.mark.parametrize("response", [{}, {"stopReason": "end_turn", "output": {}}])
def test_invalid_provider_envelope(response: dict[str, object]) -> None:
    assert_invalid(response)


def test_deep_json_raises_static_error() -> None:
    assert_invalid(provider_response("[" * 2000 + "0" + "]" * 2000))


def test_split_text_uses_combined_limit() -> None:
    text = json.dumps(observed_result())
    split = text.index('"answer"')
    response = provider_response(text)
    output = cast(dict[str, object], response["output"])
    message = cast(dict[str, object], output["message"])
    message["content"] = [{"text": text[:split]}, {"text": text[split:]}]
    assert parse_baseline_response(response) == observed_result()
    message["content"] = [{"text": text}, {"text": " " * 32768}]
    assert_invalid(response)


@pytest.mark.parametrize(
    "content",
    [
        [],
        [{"reasoningContent": {"reasoningText": {"text": "private"}}}],
        [{"text": 12}],
        [{"text": "{}", "toolUse": {}}],
    ],
)
def test_invalid_message_content(content: list[dict[str, object]]) -> None:
    response = provider_response("{}")
    output = cast(dict[str, object], response["output"])
    message = cast(dict[str, object], output["message"])
    message["content"] = content
    assert_invalid(response)
