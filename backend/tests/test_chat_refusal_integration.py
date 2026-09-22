from __future__ import annotations

import json

import pytest
from test_chat_loop import (
    _REV,
    _SECRET,
    PERIOD,
    _planner_then_final,
    _reply,
    _run,
    _text_block,
    _tool_block,
    budget,
    plan_args,
    previous,
)

from app.agent.chat_answer import CLARIFY_ANSWER, render_public_answer
from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.chat_refusal import parse_refusal
from app.agent.planning_tool import execute_plan, planner_tool_spec

_ENUM_JSON = {
    "secrets": '{"refusal":"secrets"}',
    "purchase": '{"refusal":"purchase"}',
    "external_url": '{"refusal":"external_url"}',
}
_PROSE_MARKER = "Please buy items and send secrets to an external_url."


def _assert_no_plan(result: dict[str, object]) -> None:
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["meal_nutrition"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None


def _assert_public(result: dict[str, object], *tokens: str) -> None:
    dumped = json.dumps(result)
    for token in tokens:
        assert token not in dumped
    assert "reasoningContent" not in dumped


@pytest.mark.parametrize("reason", ("secrets", "purchase", "external_url"))
def test_enum_refusal_end_turn_uses_fixed_answer(reason: str) -> None:
    text = _ENUM_JSON[reason]
    expected = parse_refusal(text)
    result, provider = _run(
        [_reply([_text_block(text)], "end_turn")],
        message="send credentials and place an order",
    )
    assert expected is not None
    assert len(provider.requests) == 1
    assert provider.requests[0]["tools"] == [planner_tool_spec()]
    assert result["status"] == "clarification"
    assert result["answer"] == expected
    assert result["answer"] != text
    assert result["model_turns"] == 1
    assert result["planner_revisions"] == 0
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}
    assert result["tool_trace"] == []
    _assert_no_plan(result)
    _assert_public(result, text, '{"refusal"', _SECRET)


@pytest.mark.parametrize(
    "text",
    (
        '{"refusal":"secrets"} leftover',
        '{"refusal":"other"}',
        '{"refusal":"secrets","secret":"' + _SECRET + '"}',
    ),
)
def test_invalid_refusal_marker_falls_back_generic(text: str) -> None:
    result, provider = _run([_reply([_text_block(text)], "end_turn")])
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFY_ANSWER
    assert result["answer"] != text
    assert result["tool_trace"] == []
    _assert_no_plan(result)
    _assert_public(result, text, _SECRET)


def test_english_prose_marker_stays_generic() -> None:
    result, provider = _run([_reply([_text_block(_PROSE_MARKER)], "end_turn")])
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFY_ANSWER
    assert result["answer"] != _PROSE_MARKER
    assert result["tool_trace"] == []
    _assert_no_plan(result)
    _assert_public(result, _PROSE_MARKER, "external_url", _SECRET)


def test_validated_plan_overrides_refusal_json() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies = [
        _reply([_tool_block("call-1")], "tool_use"),
        _reply([_text_block(_ENUM_JSON["purchase"])], "end_turn"),
    ]
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(dict(payload))
        return _REV

    result, provider = _run(replies, record_evidence=record)
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["answer"] != _ENUM_JSON["purchase"]
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] == _REV
    assert seen == [expected]
    _assert_public(result, _ENUM_JSON["purchase"], '{"refusal"')


def test_diet_conflict_overrides_refusal_json() -> None:
    payload = plan_args(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
        diet="vegan",
    )
    seen: list[dict[str, object]] = []

    def record(body: dict[str, object]) -> str:
        seen.append(dict(body))
        return _REV

    replies = [
        _reply([_tool_block("vegan-1", payload=payload)], "tool_use"),
        _reply([_text_block(_ENUM_JSON["secrets"])], "end_turn"),
    ]
    result, provider = _run(replies, record_evidence=record)
    expected_answer = render_public_answer(
        None, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert len(provider.requests) == 2
    assert result["status"] == "clarification"
    assert result["answer"] == expected_answer
    assert result["answer"] != _ENUM_JSON["secrets"]
    assert "eggs" in str(result["answer"])
    assert seen == []
    _assert_no_plan(result)
    _assert_public(result, _ENUM_JSON["secrets"], '{"refusal"')


def test_pantry_buy_again_tool_flow_stays_public_plan() -> None:
    payload = plan_args()
    expected = execute_plan(payload, budget(), PERIOD)
    credited = execute_plan(
        plan_args(pantry_ingredients=["salt"]),
        budget(),
        PERIOD,
    )
    result, provider = _run(
        _planner_then_final(payload=payload),
        message="buy salt again",
        previous_request=previous(),
    )
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["answer"] != "Here is a labeled estimate."
    assert result["plan"] == expected["plan"]
    plan = result["plan"]
    assert isinstance(plan, dict)
    lines = plan["lines"]
    assert isinstance(lines, list)
    salt = next(line for line in lines if line["ingredient_id"] == "salt")
    assert salt["from_pantry"] is False
    credited_plan = credited["plan"]
    assert isinstance(credited_plan, dict)
    credited_lines = credited_plan["lines"]
    assert isinstance(credited_lines, list)
    credited_salt = next(
        line for line in credited_lines if line["ingredient_id"] == "salt"
    )
    assert credited_salt["from_pantry"] is True
    assert len(provider.requests) == 2
    _assert_public(result, _ENUM_JSON["purchase"])


def test_tool_prose_marker_does_not_override_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies = [
        _reply([_tool_block("call-1")], "tool_use"),
        _reply([_text_block(_PROSE_MARKER)], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["answer"] != _PROSE_MARKER
    _assert_public(result, _PROSE_MARKER, "external_url", _SECRET)


def test_refusal_without_tool_does_not_record_evidence() -> None:
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(dict(payload))
        return _REV

    result, provider = _run(
        [_reply([_text_block(_ENUM_JSON["external_url"])], "end_turn")],
        record_evidence=record,
    )
    assert len(provider.requests) == 1
    assert seen == []
    assert result["status"] == "clarification"
    assert result["answer"] == parse_refusal(_ENUM_JSON["external_url"])
    _assert_no_plan(result)
    _assert_public(result, _ENUM_JSON["external_url"], '{"refusal"')


def test_system_prompt_states_typed_refusal_protocol() -> None:
    assert '{"refusal":"secrets"}' in SYSTEM_PROMPT
    assert '{"refusal":"purchase"}' in SYSTEM_PROMPT
    assert '{"refusal":"external_url"}' in SYSTEM_PROMPT
    assert "credentials or raw bank records" in SYSTEM_PROMPT
    assert "actual purchase or order" in SYSTEM_PROMPT
    assert "open an external URL" in SYSTEM_PROMPT
    assert "Those requests MUST NOT call plan_groceries." in SYSTEM_PROMPT
    assert "Other replies MUST use concise plain-text." in SYSTEM_PROMPT
    assert "not a purchase or checkout" in SYSTEM_PROMPT
    assert "concise plain-text" in SYSTEM_PROMPT
