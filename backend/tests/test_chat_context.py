from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from typing import cast

import pytest
from botocore.exceptions import ParamValidationError
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent.chat_context import (
    MAX_HISTORY,
    MAX_MESSAGE_LEN,
    build_messages,
    read_usage,
)
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


def _assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def _context(messages: list[dict[str, object]]) -> dict[str, object]:
    last = messages[-1]
    content = last["content"]
    assert isinstance(content, list)
    block = content[1]
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
    assert content[0] == {"text": "use two servings"}
    payload = _context(messages)
    assert set(payload) == {"budget", "period", "previous_request"}
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
        "now", snapshot, PERIOD, previous_request=prev, history=history
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
        ({"period": datetime(2026, 9, 1, tzinfo=UTC)}, "2026-09-01"),
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


def test_build_messages_accepts_manual_and_rejects_unknown_source() -> None:
    messages = build_messages("ok", budget(), PERIOD, spending_source="manual")
    assert messages[0]["role"] == "user"
    with pytest.raises(ChatProtocolError) as caught:
        build_messages("ok", budget(), PERIOD, spending_source="unknown")
    _assert_static(caught.value, "unknown")
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
