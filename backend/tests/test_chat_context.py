from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from typing import cast

import pytest
from botocore.exceptions import ParamValidationError
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent.catalog_tool import execute_catalog_search, next_search_arguments
from app.agent.chat_context import (
    MAX_HISTORY,
    MAX_MESSAGE_LEN,
    build_messages,
    is_modified_search_continuation,
    is_new_search_request,
    is_search_continuation,
    is_search_restart,
    more_type_query,
    plan_ingredient_ids,
    read_usage,
    restart_type_query,
)
from app.agent.chat_messages import ChatProtocolError
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import GroceryRequest

PERIOD = date(2026, 9, 1)
_SECRET = "do-not-echo-raw-input"
_ROLE = (
    "previous_request is prior state; apply latest explicit additions and removals"
    "; plan_meals is the user's current plan"
    "; previous_search holds the search_meals arguments for the next page of the "
    "last search; use them unchanged only for an explicit more request with "
    "no new restrictions"
)


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
    assert content[-1] == {"text": "use two servings"}
    payload = _context(messages)
    assert set(payload) == {
        "budget",
        "context_role",
        "period",
        "plan_cap_cents",
        "plan_meals",
        "previous_request",
        "previous_search",
        "previous_ingredient_ids",
    }
    assert payload["previous_search"] is None
    assert payload["plan_cap_cents"] is None
    assert payload["plan_meals"] is None
    assert payload["previous_ingredient_ids"] is None
    assert payload["context_role"] == _ROLE
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


def test_plan_meals_reach_the_context_in_order() -> None:
    meals: list[dict[str, object]] = [
        {"recipe_id": "bean_tacos", "servings": 2},
        {"recipe_id": "chicken_tacos", "servings": 8},
    ]
    payload = _context(build_messages("hi", budget(), PERIOD, plan_meals=meals))
    assert payload["plan_meals"] == meals
    single = _context(
        build_messages(
            "hi",
            budget(),
            PERIOD,
            plan_meals=[{"recipe_id": "bean_tacos", "servings": 2}],
        )
    )
    assert single["plan_meals"] == [{"recipe_id": "bean_tacos", "servings": 2}]
    assert _context(build_messages("hi", budget(), PERIOD))["plan_meals"] is None


@pytest.mark.parametrize(
    "message",
    ["more", "MORE!", "more meals, please", "Show me more options.", "next page"],
)
@pytest.mark.parametrize("prefixed", [False, True])
def test_explicit_more_accepts_the_client_plan_prefix(
    message: str, prefixed: bool
) -> None:
    prefix = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
    assert is_search_continuation(f"{prefix if prefixed else ''}{message}")
    assert not is_modified_search_continuation(f"{prefix if prefixed else ''}{message}")


@pytest.mark.parametrize(
    "message",
    [
        "more vegan meals",
        "more protein",
        "more, but vegan",
        "more, but no eggs",
        "more, but without chicken",
        "more, but omnivore",
        "more only vegan",
        "more instead omnivore",
        "more exclude chicken",
        "next page without rice",
        "show me more under $5",
        "how much more budget do I have?",
        "find chicken meals instead",
        "more rice onion",
        "My current plan: more",
    ],
)
@pytest.mark.parametrize("prefixed", [False, True])
def test_changed_searches_are_not_plain_continuations(
    message: str, prefixed: bool
) -> None:
    prefix = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
    assert not is_search_continuation(f"{prefix if prefixed else ''}{message}")


@pytest.mark.parametrize(
    ("message", "modified"),
    [
        ("more, but vegan", True),
        ("more, but without chicken", True),
        ("more, but omnivore", True),
        ("more only vegan", True),
        ("more instead omnivore", True),
        ("more without chicken", True),
        ("more exclude chicken", True),
        ("show me more options, but vegan", True),
        ("please give me more choices, please, only vegan", True),
        ("next page without rice", True),
        ("  MORE,\tBUT vegan!  ", True),
        ("more protein", False),
        ("more vegan meals", False),
        ("morebut vegan", False),
        ("more butternut squash", False),
        ("more onlyish vegan", False),
        ("what is my remaining budget?", False),
        ("what is in bean tacos?", False),
        ("thanks", False),
        ("how much protein is in my meal", False),
        ("My current plan: more, but vegan", False),
    ],
)
@pytest.mark.parametrize("prefixed", [False, True])
def test_continuation_modifiers_use_the_user_body(
    message: str, modified: bool, prefixed: bool
) -> None:
    prefix = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
    assert (
        is_modified_search_continuation(f"{prefix if prefixed else ''}{message}")
        is modified
    )


@pytest.mark.parametrize(
    ("message", "restart", "query"),
    [
        ("Start over from the first page", True, None),
        ("Show the first page again", True, None),
        ("Start over.", True, None),
        ("Please, start over from the first page!", True, None),
        ("Start over from the first page, please.", True, None),
        ("SHOW THE FIRST PAGE AGAIN!", True, None),
        ("Please give me the first page again.", True, None),
        ("First page, please.", True, None),
        ("Go back to the first page.", True, None),
        ("Please start from the first page.", True, None),
        ("Start at the first page, please!", True, None),
        ("Go to the first page.", True, None),
        ("Restart the search.", True, None),
        ("Start again at the beginning.", True, None),
        ("Start over with vegan meals.", True, "vegan"),
        (
            "Please, start over from the first page with vegan meals!",
            True,
            "vegan",
        ),
        (
            "Show me the first page of gluten free meals again, please.",
            True,
            "gluten free",
        ),
        ("Show the first page of gluten-free meals", True, "gluten-free"),
        ("Show the first page of celiac meals", True, "celiac"),
        (
            "Show the first page of gluten free ingredients meals",
            True,
            "gluten free ingredients",
        ),
        (
            "Find high protein vegetarian meals from the first page.",
            True,
            "high protein vegetarian",
        ),
        ("Show vegan meals again", True, "vegan"),
        ("Show me the first page of rice onion meals.", True, "rice onion"),
        ("Show me the first page of onion rice meals.", True, "onion rice"),
        (
            "Please, start over from the first page with rice onion meals!",
            True,
            "rice onion",
        ),
        ("Restart the search for rice onion recipes, please.", True, "rice onion"),
        ("Start again at the beginning with rice onion meals.", True, "rice onion"),
        ("Show rice onion meals again.", True, "rice onion"),
        ("Find rice onion ideas from the first page.", True, "rice onion"),
        ("Give me rice meals at the first page, please!", True, "rice"),
        ("Start over with onion meals.", True, "onion"),
        ("Please show the first page of pasta recipes again!", True, "pasta"),
        ("What is my budget at the start of the month?", False, None),
        ("Show my budget first.", False, None),
        ("Start with my budget.", False, None),
        ("What is in my first meal?", False, None),
        ("Show my first meal again.", False, None),
        ("Show the first page of my plan.", False, None),
        ("First show me my meal.", False, None),
        ("Find vegan meals and start over.", False, None),
        ("Show the first page again and my budget.", False, None),
        ("Restart my meal.", False, None),
        ("More vegetarian.", False, None),
        ("My current plan: start over", False, None),
        ("Show the first page of unsupported meals", False, None),
        ("Start over with unsupported meals", False, None),
        ("Show me the first page of zqxsentinel meals.", False, None),
        ("Show me the first page of rice zqxsentinel meals.", False, None),
        ("Start over with zqxsentinel onion meals.", False, None),
        ("Find rice zqxsentinel meals again.", False, None),
        ("Show the first page of paleo rice meals.", False, None),
        ("Show the first page of gluten free zqxsentinel meals.", False, None),
        ("Show the first page of gluten free paleo meals.", False, None),
        ("Find gluten free pasta meals from the first page.", False, None),
        ("Show me the first page of rice onion meals and my budget.", False, None),
        ("What is in my rice meal?", False, None),
    ],
)
@pytest.mark.parametrize("prefixed", [False, True])
def test_search_restarts_use_bounded_forms_in_the_user_body(
    message: str, restart: bool, query: str | None, prefixed: bool
) -> None:
    prefix = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
    full_message = f"{prefix if prefixed else ''}{message}"
    assert is_search_restart(full_message) is restart
    assert restart_type_query(full_message) == query
    if restart:
        assert not is_search_continuation(full_message)
        assert not is_modified_search_continuation(full_message)


@pytest.mark.parametrize(
    ("message", "new_search"),
    [
        ("Find vegan meals", True),
        ("vegan", True),
        ("chicken", True),
        ("omnivore", True),
        ("gluten free", True),
        ("egg", True),
        ("beans", True),
        ("lentils", True),
        ("chickpeas", True),
        ("Find high protein vegetarian meals.", True),
        ("gluten free ingredients vegetarian", True),
        ("show me chicken options, please!", True),
        ("Please, give me plant-based recipes.", True),
        ("Find omnivore ideas", True),
        ("  SHOW\tvegan meals! Please.  ", True),
        ("more vegan", True),
        ("More gluten free meals, please", True),
        ("show me more vegan meals", True),
        ("Show me the vegan ones", True),
        ("show me the gluten free ones please", True),
        ("Start over with vegan meals", True),
        ("Show the first page of vegetarian meals", True),
        ("Find gluten free meals from the first page", True),
        ("Show the first page of gluten-free meals", True),
        ("Show the first page of celiac meals", True),
        ("Show me the first page of rice onion meals.", True),
        ("Restart the search for onion meals.", True),
        ("Start over from the first page", False),
        ("Show the first page again", False),
        ("more meals", False),
        ("show me more options", False),
        ("more please", False),
        ("more xyzzy", False),
        ("more butternut squash", False),
        ("more vegan for my plan", False),
        ("How much protein is in my meal?", False),
        ("Is my current meal vegan?", False),
        ("what is in chicken tacos?", False),
        ("what is my remaining budget?", False),
        ("thanks", False),
        ("more", False),
        ("more, but vegan", False),
        ("Find unsupported meals", False),
        ("Show me the first page of rice zqxsentinel meals.", False),
        ("Find gluten free pasta meals from the first page.", False),
        ("Show the first page of paleo rice meals.", False),
        ("Show the first page of gluten free zqxsentinel meals.", False),
        ("Show the first page of gluten free paleo meals.", False),
        ("rice onion", False),
        ("more rice onion", False),
        ("Find vegan meals for my plan", False),
        ("My current plan: vegan", False),
    ],
)
@pytest.mark.parametrize("prefixed", [False, True])
def test_explicit_type_requests_use_the_user_body(
    message: str, new_search: bool, prefixed: bool
) -> None:
    prefix = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
    assert is_new_search_request(f"{prefix if prefixed else ''}{message}") is new_search


@pytest.mark.parametrize(
    ("message", "query"),
    [
        ("more vegan", "vegan"),
        ("Show me more gluten free meals, please", "gluten free"),
        ("show me the vegan ones", "vegan"),
        ("more", None),
        ("more meals", None),
        ("more, but vegan", None),
        ("more without chicken", None),
        ("more rice onion", None),
        ("vegan", None),
    ],
)
def test_more_type_query_returns_the_meal_terms_of_the_request(
    message: str, query: str | None
) -> None:
    assert more_type_query(message) == query


def test_checked_search_context_keeps_every_facet_and_offset() -> None:
    found = execute_catalog_search(
        {
            "query": "gluten free",
            "diet": "vegetarian",
            "exclude": ["eggs"],
            "min_protein_g": 0,
            "max_cents_per_serving": 10000,
            "limit": 3,
        }
    )
    search = next_search_arguments(found)
    assert search is not None and search["offset"] == 3
    original = copy.deepcopy(search)
    messages = build_messages("more", budget(), PERIOD, previous_search=search)
    assert _context(messages)["previous_search"] == original
    search["tags"] = []
    assert _context(messages)["previous_search"] == original


@pytest.mark.parametrize(
    "search",
    [
        {"query": "meals", "tags": ["unknown"]},
        {"query": "vegetarian", "offset": 40},
        {"query": "vegetarian", "offset": True},
        {"query": "zqxsentinel"},
    ],
)
def test_invalid_restored_search_is_rejected(search: dict[str, object]) -> None:
    with pytest.raises(ChatProtocolError, match="previous_search is invalid"):
        build_messages("more", budget(), PERIOD, previous_search=search)


@pytest.mark.parametrize(
    "plan_meals",
    [
        [{"recipe_id": "not_a_recipe", "servings": 2}],
        [{"recipe_id": "bean_tacos", "servings": 9}],
        [{"recipe_id": "bean_tacos", "servings": 0}],
        [{"recipe_id": "bean_tacos", "servings": True}],
        [{"recipe_id": "bean_tacos", "servings": "2"}],
        [{"recipe_id": 7, "servings": 2}],
        [{"servings": 2}],
        ["bean_tacos"],
        [{"recipe_id": "bean_tacos", "servings": 1}] * 4,
    ],
)
def test_invalid_plan_meals_raise(plan_meals: list[dict[str, object]]) -> None:
    with pytest.raises(ChatProtocolError):
        build_messages("hi", budget(), PERIOD, plan_meals=plan_meals)


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
        ({"plan_cap_cents": -1}, "-1"),
        ({"plan_cap_cents": True}, "True"),
        ({"plan_cap_cents": False}, "False"),
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


def test_read_usage_copies_cache_counts_and_drops_unrelated_fields() -> None:
    counts = {
        "inputTokens": 3,
        "outputTokens": 5,
        "cacheReadInputTokens": 0,
        "cacheWriteInputTokens": 7,
    }
    response = {"usage": {**counts, "totalTokens": 15, "reasoningContent": "hidden"}}
    result = read_usage(response)
    assert result == counts
    response["usage"]["cacheWriteInputTokens"] = 99
    assert result == counts


@pytest.mark.parametrize("key", ["cacheReadInputTokens", "cacheWriteInputTokens"])
@pytest.mark.parametrize("value", [None, True, False, -1, 1.5, 1.0, "2", [], {}])
def test_invalid_cache_count_stays_unknown(key: str, value: object) -> None:
    other = (
        "cacheWriteInputTokens"
        if key == "cacheReadInputTokens"
        else "cacheReadInputTokens"
    )
    expected = {"inputTokens": 3, "outputTokens": 5, other: 0}
    assert read_usage({"usage": {**expected, key: value}}) == expected


def test_plan_cap_zero_none_and_positive_stay_explicit() -> None:
    none_messages = build_messages("ok", budget(available_cents=10_000), PERIOD)
    none_payload = _context(none_messages)
    none_content = none_messages[0]["content"]
    assert isinstance(none_content, list)
    none_block = none_content[0]
    assert isinstance(none_block, dict)
    none_text = none_block["text"]
    assert isinstance(none_text, str)
    assert none_payload["plan_cap_cents"] is None
    assert none_payload["budget"]["available_cents"] == 10_000
    assert '"plan_cap_cents":null' in none_text
    assert '"plan_cap_cents":10000' not in none_text
    zero_payload = _context(
        build_messages("ok", budget(available_cents=10_000), PERIOD, plan_cap_cents=0)
    )
    assert zero_payload["plan_cap_cents"] == 0
    assert zero_payload["budget"]["available_cents"] == 10_000
    positive = _context(
        build_messages("ok", budget(available_cents=10_000), PERIOD, plan_cap_cents=500)
    )
    assert positive["plan_cap_cents"] == 500
    assert positive["budget"]["available_cents"] == 10_000


def test_previous_pantry_structure_and_context_before_user_message() -> None:
    prev = previous(pantry_ingredients=["salt", "oil"])
    messages = build_messages(
        "add rice and remove oil",
        budget(),
        PERIOD,
        previous_request=prev,
        history=pair(0),
        plan_cap_cents=2_000,
    )
    assert messages[0] == {"role": "user", "content": [{"text": "user-0"}]}
    assert messages[1]["role"] == "assistant"
    last = messages[-1]
    assert last["role"] == "user"
    content = last["content"]
    assert isinstance(content, list)
    assert content[-1] == {"text": "add rice and remove oil"}
    payload = _context(messages)
    assert payload["plan_cap_cents"] == 2_000
    assert payload["context_role"] == _ROLE
    assert payload["previous_request"] == GroceryRequest.model_validate(
        prev
    ).model_dump(mode="json")
    previous_payload = payload["previous_request"]
    assert isinstance(previous_payload, dict)
    assert previous_payload["pantry_ingredients"] == ["salt", "oil"]


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ({"lines": [{"ingredient_id": "eggs"}]}, ["eggs"]),
        (
            {
                "lines": [
                    {"ingredient_id": "tortillas"},
                    {"ingredient_id": "eggs"},
                    {"ingredient_id": "eggs"},
                    {"ingredient_id": "unknown"},
                    {"ingredient_id": []},
                    {},
                    "eggs",
                ]
            },
            ["eggs", "tortillas"],
        ),
        ({"lines": []}, []),
        ({"lines": [{"ingredient_id": "unknown"}]}, []),
        ({"lines": None}, None),
        ({}, None),
        (None, None),
        ([], None),
    ],
)
def test_plan_ingredient_ids(plan: object, expected: list[str] | None) -> None:
    assert plan_ingredient_ids(plan) == expected


def test_previous_ingredient_ids_are_sorted_without_mutation() -> None:
    ids = ["tortillas", "eggs"]
    payload = _context(
        build_messages("make it vegan", budget(), PERIOD, previous_ingredient_ids=ids)
    )
    assert payload["previous_ingredient_ids"] == ["eggs", "tortillas"]
    assert ids == ["tortillas", "eggs"]
    first_payload = _context(build_messages("hello", budget(), PERIOD))
    assert first_payload["previous_ingredient_ids"] is None
    assert (
        _context(build_messages("hello", budget(), PERIOD, previous_ingredient_ids=[]))[
            "previous_ingredient_ids"
        ]
        == []
    )


@pytest.mark.parametrize(
    "ids",
    ["eggs", ("eggs",), ["unknown"], [[]], [1], ["eggs"] * (len(INGREDIENTS) + 1)],
)
def test_invalid_previous_ingredient_ids_raise_static_error(ids: object) -> None:
    with pytest.raises(ChatProtocolError, match="previous_request is invalid"):
        build_messages(
            "hello", budget(), PERIOD, previous_ingredient_ids=cast(list[str], ids)
        )
