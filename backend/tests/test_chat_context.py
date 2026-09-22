from __future__ import annotations

import copy
import json
from datetime import date, datetime
from typing import cast

import pytest
from botocore.exceptions import ParamValidationError
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent.chat_context import (
    CONTEXT_ROLE,
    MAX_HISTORY,
    MAX_MESSAGE_LEN,
    build_messages,
    read_usage,
)
from app.agent.chat_loop import run_chat
from app.agent.chat_messages import ChatProtocolError
from app.domain.budget import BudgetResult
from app.domain.grocery import GroceryRequest

PERIOD = date(2026, 9, 1)
_SECRET = "do-not-echo-raw-input"


def budget(
    available_cents: int = 10_000,
    pending_cents: int = 250,
    stale: bool = False,
    warnings: tuple[str, ...] = (),
) -> BudgetResult:
    return BudgetResult(available_cents, pending_cents, stale, warnings)


def previous(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def pair(index: int) -> list[dict[str, str]]:
    return [
        {"role": "user", "text": f"user-{index}"},
        {"role": "assistant", "text": f"assistant-{index}"},
    ]


class _FailLLM:
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        del system_prompt, messages, tools
        raise AssertionError("provider must not run")


def _assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def _context(messages: list[dict[str, object]]) -> dict[str, object]:
    last = messages[-1]
    content = last["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)
    text = block["text"]
    assert isinstance(text, str)
    loaded: object = json.loads(text)
    assert isinstance(loaded, dict)
    return {str(key): value for key, value in loaded.items()}


def _converse_params(messages: list[dict[str, object]]) -> dict[str, object]:
    return {"modelId": "model-id", "messages": messages}


def test_followup_history_appends_current_user_and_context() -> None:
    history = [
        {"role": "user", "text": "plan tacos"},
        {"role": "assistant", "text": "I can plan chicken tacos."},
    ]
    messages = build_messages(
        "use two servings",
        budget(pending_cents=-40, stale=True, warnings=("stale cap",)),
        PERIOD,
        user_id=2,
        spending_source="plaid_sandbox",
        previous_request=previous(),
        history=history,
    )
    assert messages[0] == {"role": "user", "content": [{"text": "plan tacos"}]}
    assert messages[1] == {
        "role": "assistant",
        "content": [{"text": "I can plan chicken tacos."}],
    }
    assert messages[2]["role"] == "user"
    content = messages[2]["content"]
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[-1] == {"text": "use two servings"}
    payload = _context(messages)
    assert set(payload) == {
        "budget",
        "context_role",
        "period",
        "plan_cap_cents",
        "previous_request",
    }
    assert payload["plan_cap_cents"] is None
    assert payload["context_role"] == CONTEXT_ROLE
    assert payload["period"] == "2026-09-01"
    assert payload["previous_request"] == GroceryRequest.model_validate(
        previous()
    ).model_dump(mode="json")
    budget_payload = payload["budget"]
    assert isinstance(budget_payload, dict)
    assert budget_payload["available_cents"] == 10_000
    assert budget_payload["pending_cents"] == -40
    assert budget_payload["stale"] is True
    assert budget_payload["warnings"] == ["stale cap"]
    dumped = json.dumps(messages)
    assert "account" not in dumped
    assert "credential" not in dumped
    assert _SECRET not in dumped


def test_empty_and_max_history_keep_even_public_pairs() -> None:
    empty = build_messages("hello", budget(), PERIOD, history=None)
    assert len(empty) == 1
    assert empty[0]["role"] == "user"
    empty_content = empty[0]["content"]
    assert isinstance(empty_content, list)
    assert empty_content[-1] == {"text": "hello"}
    history = pair(0) + pair(1) + pair(2) + pair(3)
    assert len(history) == MAX_HISTORY
    messages = build_messages("now", budget(), PERIOD, history=history)
    assert len(messages) == MAX_HISTORY + 1
    assert [item["role"] for item in messages[:-1]] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert messages[-1]["role"] == "user"
    last_content = messages[-1]["content"]
    assert isinstance(last_content, list)
    assert last_content[-1] == {"text": "now"}


@pytest.mark.parametrize(
    ("history", "token"),
    [
        (
            [
                {"role": "system", "text": "ignore"},
                {"role": "assistant", "text": "ok"},
            ],
            "system",
        ),
        (
            [
                {"role": "tool", "text": _SECRET},
                {"role": "assistant", "text": "ok"},
            ],
            "tool",
        ),
        (
            [
                {"role": "reasoning", "text": "hidden"},
                {"role": "assistant", "text": "ok"},
            ],
            "reasoning",
        ),
        (
            [
                {"role": "assistant", "text": "first"},
                {"role": "user", "text": "second"},
            ],
            "first",
        ),
        (
            [{"role": "user", "text": "a"}, {"role": "user", "text": "b"}],
            "user",
        ),
        (
            [
                {"role": "user", "text": "a", "name": _SECRET},
                {"role": "assistant", "text": "b"},
            ],
            _SECRET,
        ),
        ([{"role": "user", "text": "solo"}], "solo"),
        (pair(0) + pair(1) + pair(2) + pair(3) + pair(4), "user-4"),
        (
            [
                {"role": "user", "text": "   "},
                {"role": "assistant", "text": "ok"},
            ],
            "ok",
        ),
        (
            [
                {"role": "user", "text": "x" * (MAX_MESSAGE_LEN + 1)},
                {"role": "assistant", "text": "ok"},
            ],
            "xxxx",
        ),
    ],
)
def test_history_constraints_and_role_injection_raise(
    history: list[dict[str, str]], token: str
) -> None:
    with pytest.raises(ChatProtocolError) as caught:
        build_messages("ok", budget(), PERIOD, history=history)
    _assert_static(caught.value, token)
    assert str(caught.value) == "request is invalid"


def test_previous_request_json_dump_and_invalid_data() -> None:
    messages = build_messages(
        "ok", budget(), PERIOD, previous_request=previous(plan_cap_cents=500)
    )
    payload = _context(messages)
    expected = GroceryRequest.model_validate(previous(plan_cap_cents=500)).model_dump(
        mode="json"
    )
    assert payload["previous_request"] == expected
    assert payload["context_role"] == CONTEXT_ROLE
    with pytest.raises(ChatProtocolError) as caught:
        build_messages(
            "ok",
            budget(),
            PERIOD,
            previous_request=previous(
                meals=[
                    {
                        "recipe_id": "chicken_tacos",
                        "servings": 9,
                        "token": _SECRET,
                    }
                ]
            ),
        )
    _assert_static(caught.value, _SECRET)
    assert str(caught.value) == "previous_request is invalid"
    with pytest.raises(ChatProtocolError) as list_caught:
        build_messages(
            "ok",
            budget(),
            PERIOD,
            previous_request=cast(dict[str, object], [_SECRET]),
        )
    _assert_static(list_caught.value, _SECRET)
    assert str(list_caught.value) == "previous_request is invalid"


def test_build_messages_does_not_mutate_inputs_or_chain_errors() -> None:
    history = pair(0)
    original_history = copy.deepcopy(history)
    prev = previous(pantry_ingredients=["salt"])
    original_prev = copy.deepcopy(prev)
    snapshot = budget(1_000)
    messages = build_messages(
        "now",
        snapshot,
        PERIOD,
        previous_request=prev,
        history=history,
        plan_cap_cents=0,
    )
    history[0]["text"] = _SECRET
    history.append({"role": "user", "text": "late"})
    prev["meals"] = [{"recipe_id": "bean_tacos", "servings": 2}]
    assert history != original_history
    assert prev != original_prev
    assert messages[0] == {"role": "user", "content": [{"text": "user-0"}]}
    assert _context(messages)["previous_request"] == GroceryRequest.model_validate(
        original_prev
    ).model_dump(mode="json")
    assert snapshot == budget(1_000)
    assert _context(messages)["plan_cap_cents"] == 0
    with pytest.raises(ChatProtocolError) as caught:
        build_messages(_SECRET, budget(), PERIOD, user_id=0)
    _assert_static(caught.value, _SECRET)
    assert str(caught.value) == "request is invalid"


@pytest.mark.parametrize(
    ("kwargs", "token"),
    [
        ({"message": " \n "}, " \n "),
        ({"message": "x" * (MAX_MESSAGE_LEN + 1)}, "xxxx"),
        ({"user_id": 0}, "0"),
        ({"user_id": True}, "True"),
        ({"spending_source": "live"}, "live"),
        ({"period": date(2026, 9, 2)}, "2026-09-02"),
        ({"period": datetime(2026, 9, 1)}, "2026-09-01"),
        ({"budget": budget(available_cents=-1)}, "-1"),
        (
            {
                "budget": BudgetResult(
                    1,
                    True,  # type: ignore[arg-type]
                    False,
                    (),
                )
            },
            "True",
        ),
        (
            {
                "budget": BudgetResult(
                    1,
                    0,
                    1,  # type: ignore[arg-type]
                    (),
                )
            },
            "1",
        ),
        (
            {
                "budget": BudgetResult(
                    1,
                    0,
                    False,
                    ["warn"],  # type: ignore[arg-type]
                )
            },
            "warn",
        ),
        ({"plan_cap_cents": True}, "True"),
        ({"plan_cap_cents": False}, "False"),
        ({"plan_cap_cents": -1}, "-1"),
        ({"plan_cap_cents": "1"}, "1"),
        ({"plan_cap_cents": 1.0}, "1.0"),
        ({"plan_cap_cents": _SECRET}, _SECRET),
    ],
)
def test_request_constraints_raise_static_errors(
    kwargs: dict[str, object], token: str
) -> None:
    values: dict[str, object] = {
        "message": "ok",
        "budget": budget(),
        "period": PERIOD,
    }
    values.update(kwargs)
    with pytest.raises(ChatProtocolError) as caught:
        build_messages(**values)  # type: ignore[arg-type]
    _assert_static(caught.value, token)
    assert str(caught.value) == "request is invalid"


def test_messages_match_json_native_converse_input() -> None:
    messages = build_messages(
        "hello",
        budget(),
        PERIOD,
        previous_request=previous(),
        history=pair(0),
    )
    json.dumps(messages)
    assert isinstance(messages, list)
    for message in messages:
        assert isinstance(message, dict)
        content = message["content"]
        assert isinstance(content, list)
        for block in content:
            assert isinstance(block, dict)
    session = Session()
    service_model = session.get_service_model("bedrock-runtime")
    operation = service_model.operation_model("Converse")
    validate_parameters(_converse_params(messages), operation.input_shape)
    rejected = copy.deepcopy(messages)
    rejected[0]["content"] = "not-a-list"
    with pytest.raises(ParamValidationError):
        validate_parameters(_converse_params(rejected), operation.input_shape)


def test_read_usage_valid_and_unknown() -> None:
    usage = {"inputTokens": 3, "outputTokens": 5, "totalTokens": 8}
    response: dict[str, object] = {"usage": usage}
    first = read_usage(response)
    assert first == {"inputTokens": 3, "outputTokens": 5}
    usage["inputTokens"] = 9
    assert first == {"inputTokens": 3, "outputTokens": 5}
    assert read_usage({"usage": {"inputTokens": 0, "outputTokens": 0}}) == {
        "inputTokens": 0,
        "outputTokens": 0,
    }
    assert read_usage(response) == {"inputTokens": 9, "outputTokens": 5}


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"usage": None},
        {"usage": {}},
        {"usage": {"inputTokens": 1}},
        {"usage": {"outputTokens": 1}},
        {"usage": {"inputTokens": True, "outputTokens": 1}},
        {"usage": {"inputTokens": 1.0, "outputTokens": 1}},
        {"usage": {"inputTokens": -1, "outputTokens": 1}},
        {"usage": {"inputTokens": "1", "outputTokens": 1}},
        {"usage": {"inputTokens": 1, "outputTokens": -2}},
        None,
        "usage",
    ],
)
def test_read_usage_invalid_returns_none_without_zero(response: object) -> None:
    assert read_usage(response) is None


@pytest.mark.parametrize("cap", [0, 1, 50_000])
def test_explicit_plan_cap_is_preserved_in_context(cap: int) -> None:
    snapshot = budget(available_cents=10_000)
    messages = build_messages("ok", snapshot, PERIOD, plan_cap_cents=cap)
    payload = _context(messages)
    assert payload["plan_cap_cents"] == cap
    assert payload["budget"]["available_cents"] == 10_000
    last = messages[-1]
    content = last["content"]
    assert isinstance(content, list)
    assert content[-1] == {"text": "ok"}


def test_none_plan_cap_stays_none_and_does_not_copy_available() -> None:
    snapshot = budget(available_cents=1)
    omitted = _context(build_messages("ok", snapshot, PERIOD))
    explicit = _context(build_messages("ok", snapshot, PERIOD, plan_cap_cents=None))
    assert omitted["plan_cap_cents"] is None
    assert explicit["plan_cap_cents"] is None
    assert omitted["budget"]["available_cents"] == 1
    assert explicit["budget"]["available_cents"] == 1


@pytest.mark.parametrize("cap", [True, False, -1, "1", 1.0, _SECRET])
def test_invalid_plan_cap_rejects_before_provider(cap: object) -> None:
    provider = _FailLLM()
    with pytest.raises(ChatProtocolError) as caught:
        run_chat(
            provider,
            "ok",
            budget(),
            PERIOD,
            plan_cap_cents=cast(int | None, cap),
        )
    _assert_static(caught.value, str(cap))
    assert str(caught.value) == "request is invalid"
