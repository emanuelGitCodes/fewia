import copy
import json
from typing import cast

import pytest

from app.agent import chat_loop
from app.agent.catalog_tool import (
    TOOL_NAME,
    catalog_answer,
    execute_catalog_search,
    exhausted_search_arguments,
    next_search_arguments,
)
from app.agent.chat_answer import TYPE_CLARIFICATION
from app.agent.chat_context import validated_previous_exhausted_search
from app.agent.chat_loop import run_chat
from app.agent.chat_messages import ChatProtocolError, ToolCall, tool_result_block
from app.agent.chat_refusal import GUARDRAIL_DECLINE
from tests.test_chat_loop import (
    PERIOD,
    FakeLLM,
    Proposer,
    _budget_block,
    _catalog_word_cursor,
    _constrained_cursor,
    _named_facet_cursor,
    _propose_block,
    _reply,
    _search_reply,
    _text_block,
    _tool_block,
    _two_meal_revision,
    budget,
)

NO_MORE = "There are no more matching meals."
PREFIX = "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n"
BLOCKED = "blocked-search-output"


def terminal_search(arguments: dict[str, object]) -> dict[str, object]:
    first = execute_catalog_search({**arguments, "offset": 0})
    total = cast(int, first["total_matches"])
    request = cast(dict[str, object], first["request"])
    limit = cast(int, request["limit"])
    assert total > 0
    page = execute_catalog_search(
        {**arguments, "offset": (total - 1) // limit * limit},
    )
    checked = exhausted_search_arguments(page)
    assert checked is not None
    return checked


@pytest.mark.parametrize("message", ["more", "more vegetarian", "the vegetarian ones"])
@pytest.mark.parametrize(
    "model_arguments",
    [None, {}, {"query": "vegetarian", "offset": 0}, {"query": "chicken"}],
)
@pytest.mark.parametrize("model_prose", [False, True])
@pytest.mark.parametrize("prefixed", [False, True])
def test_exhausted_more_waits_for_provider_and_dispatches_nothing(
    message: str,
    model_arguments: dict[str, object] | None,
    model_prose: bool,
    prefixed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    original = copy.deepcopy(exhausted)

    def unexpected(*args: object, **kwargs: object) -> object:
        pytest.fail("An exhausted continuation MUST NOT dispatch tools")

    monkeypatch.setattr(chat_loop, "dispatch", unexpected)
    reply = (
        _reply([_text_block("Try chicken tacos.")], "end_turn")
        if model_arguments is None
        else _search_reply(model_arguments)
    )
    provider = FakeLLM([reply])
    observed: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        f"{PREFIX if prefixed else ''}{message}",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
        model_prose=model_prose,
        observe_terminal_tool_results=observed.append,
    )
    assert result["answer"] == NO_MORE
    assert result["status"] == "clarification"
    assert result["reply_source"] == "template"
    assert result["plan"] is result["request"] is None
    assert result["model_turns"] == len(provider.requests) == 1
    assert result["planner_revisions"] == 0
    assert result["tool_trace"] == observed == []
    assert "choices" not in result and "next_search" not in result
    assert result["exhausted_search"] == exhausted == original
    assert result["exhausted_search"] is not exhausted


@pytest.mark.parametrize("intervening", ["budget", "read", "no_tool", "vegan_read"])
@pytest.mark.parametrize("model_prose", [False, True])
def test_exhaustion_survives_unrelated_turns(
    intervening: str, model_prose: bool
) -> None:
    exhausted = terminal_search(_constrained_cursor())
    replies = [_reply([_text_block("Done.")], "end_turn")]
    message = "thanks"
    if intervening == "budget":
        message = "What is my budget?"
        replies.insert(0, _reply([_budget_block("b1")], "tool_use"))
    elif intervening in ("read", "vegan_read"):
        message = (
            "Is my current meal vegan?"
            if intervening == "vegan_read"
            else "What is in bean tacos?"
        )
        replies.insert(
            0,
            _reply(
                [
                    _tool_block(
                        "r1", name="get_meal", payload={"recipe_id": "bean_tacos"}
                    )
                ],
                "tool_use",
            ),
        )
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        message,
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
        model_prose=model_prose,
    )
    assert result["exhausted_search"] == exhausted
    assert "next_search" not in result and "choices" not in result
    more = run_chat(
        FakeLLM([_search_reply({"query": "chicken"})]),
        "more",
        budget(),
        PERIOD,
        previous_exhausted_search=cast(dict[str, object], result["exhausted_search"]),
        model_prose=model_prose,
    )
    assert more["answer"] == NO_MORE and more["tool_trace"] == []


@pytest.mark.parametrize("kind", ["words", "facet"])
@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize("no_tool", [False, True])
@pytest.mark.parametrize("model_prose", [False, True])
def test_restart_from_exhaustion_keeps_all_filters_and_limit(
    kind: str, named: bool, no_tool: bool, model_prose: bool
) -> None:
    cursor = _catalog_word_cursor() if kind == "words" else _named_facet_cursor()
    exhausted = terminal_search(cursor)
    original = copy.deepcopy(exhausted)
    first = {**exhausted, "offset": 0}
    message = "Start over"
    if named:
        terms = "rice onion" if kind == "words" else "gluten free"
        message = f"Show the first page of {terms} meals"
    reply = (
        _reply([_text_block("Try chicken tacos.")], "end_turn")
        if no_tool
        else _search_reply({"query": "chicken", "limit": 3, "offset": 9})
    )
    provider = FakeLLM([reply])
    observed: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        PREFIX + message,
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
        model_prose=model_prose,
        observe_terminal_tool_results=observed.append,
    )
    assert exhausted == original
    assert "exhausted_search" not in result
    if no_tool:
        assert result["answer"] == TYPE_CLARIFICATION
        assert result["next_search"] == first
        assert result["tool_trace"] == [] and "choices" not in result
        observed.clear()
        result = run_chat(
            FakeLLM([_search_reply({"query": "chicken", "limit": 3})]),
            "more",
            budget(),
            PERIOD,
            previous_search=cast(dict[str, object], result["next_search"]),
            observe_terminal_tool_results=observed.append,
        )
    expected = execute_catalog_search(first)
    assert result["choices"] == [{"recipe_id": rid} for rid in expected["recipe_ids"]]
    assert result["answer"] == catalog_answer(expected)
    assert result["next_search"] == next_search_arguments(expected)
    assert observed == [[tool_result_block("d1", expected, success=True)]]


@pytest.mark.parametrize("exhausted_state", [False, True])
@pytest.mark.parametrize(
    "message",
    [
        "more",
        "Find vegan meals",
        "more, but vegan",
        "Start over",
        "Start over with vegan meals",
    ],
)
@pytest.mark.parametrize("model_prose", [False, True])
def test_guardrail_restores_original_state_before_any_message_reset(
    exhausted_state: bool, message: str, model_prose: bool
) -> None:
    cursor = _constrained_cursor()
    exhausted = terminal_search(cursor) if exhausted_state else None
    original = copy.deepcopy(exhausted if exhausted_state else cursor)
    provider = FakeLLM([_reply([_text_block(BLOCKED)], "guardrail_intervened")])
    result = run_chat(
        provider,
        PREFIX + message,
        budget(),
        PERIOD,
        previous_search=None if exhausted_state else cursor,
        previous_exhausted_search=exhausted,
        model_prose=model_prose,
    )
    key = "exhausted_search" if exhausted_state else "next_search"
    assert result[key] == original
    assert result["answer"] == GUARDRAIL_DECLINE
    assert result["reply_check"] == ({"gate": "guardrail"} if model_prose else None)
    assert "choices" not in result and "proposal_id" not in result
    assert result["plan"] is result["request"] is None
    assert BLOCKED not in json.dumps(result)
    assert result["model_turns"] == len(provider.requests) == 1
    more = run_chat(
        FakeLLM([_search_reply({"query": "chicken"})]),
        "more",
        budget(),
        PERIOD,
        previous_search=(
            None if exhausted_state else cast(dict[str, object], result[key])
        ),
        previous_exhausted_search=(
            cast(dict[str, object], result[key]) if exhausted_state else None
        ),
    )
    if exhausted_state:
        assert more["answer"] == NO_MORE and "choices" not in more
    else:
        expected = execute_catalog_search(cursor)
        assert more["choices"] == [{"recipe_id": rid} for rid in expected["recipe_ids"]]


@pytest.mark.parametrize("exhausted_state", [False, True])
@pytest.mark.parametrize("model_prose", [False, True])
def test_guardrail_after_tool_rounds_restores_state_without_proposal(
    exhausted_state: bool, model_prose: bool
) -> None:
    cursor = _constrained_cursor()
    exhausted = terminal_search(cursor) if exhausted_state else None
    proposer = Proposer()
    provider = FakeLLM(
        [
            _reply(
                [_propose_block("p1", {"op": "remove", "recipe_id": "bean_tacos"})],
                "tool_use",
            ),
            _reply(
                [
                    _tool_block("d1", name=TOOL_NAME, payload={"query": "vegan"}),
                    _tool_block("bad", name="unsupported", payload={}),
                ],
                "tool_use",
            ),
            _reply([_text_block(BLOCKED)], "guardrail_intervened"),
        ]
    )
    result = run_chat(
        provider,
        "Find vegan meals",
        budget(),
        PERIOD,
        previous_search=None if exhausted_state else cursor,
        previous_exhausted_search=exhausted,
        plan_revision=_two_meal_revision(),
        propose=proposer,
        model_prose=model_prose,
    )
    assert result["answer"] == GUARDRAIL_DECLINE
    assert result.get("next_search") == (None if exhausted_state else cursor)
    assert result.get("exhausted_search") == exhausted
    assert result["model_turns"] == len(provider.requests) == 3
    assert proposer.calls == [[{"op": "remove", "recipe_id": "bean_tacos"}]]
    assert "proposal_id" not in result and "choices" not in result
    assert result["plan"] is result["request"] is None
    assert BLOCKED not in json.dumps(result)


@pytest.mark.parametrize(
    "message",
    ["Find vegan meals", "more, but vegan", "Start over with vegan meals"],
)
def test_new_or_modified_request_clears_exhaustion_without_tools(message: str) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    result = run_chat(
        FakeLLM([_reply([_text_block("Which meals?")], "end_turn")]),
        message,
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    assert "exhausted_search" not in result and "next_search" not in result
    more = run_chat(
        FakeLLM([_search_reply({"query": "vegetarian"})]),
        "more",
        budget(),
        PERIOD,
    )
    assert more["answer"] == TYPE_CLARIFICATION and more["tool_trace"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": "unknown"},
        {"query": "vegetarian", "exclude": ["nightshades"]},
    ],
)
def test_failed_attempted_search_clears_exhaustion(
    arguments: dict[str, object],
) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    result = run_chat(
        FakeLLM([_search_reply(arguments), _reply([_text_block("Done.")], "end_turn")]),
        "Find different meals instead",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    assert "exhausted_search" not in result and "next_search" not in result
    assert "choices" not in result


def test_failed_restart_dispatch_clears_both_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exhausted = terminal_search(_constrained_cursor())

    def failed(
        call: ToolCall, *args: object, **kwargs: object
    ) -> tuple[None, dict[str, object]]:
        return None, tool_result_block(
            call.tool_use_id, {"error": "failed"}, success=False
        )

    monkeypatch.setattr(chat_loop, "dispatch", failed)
    result = run_chat(
        FakeLLM(
            [
                _search_reply({"query": "vegetarian"}),
                _reply([_text_block("Done.")], "end_turn"),
            ]
        ),
        "Start over",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    assert "exhausted_search" not in result and "next_search" not in result


@pytest.mark.parametrize("gate", ["guardrail_intervened", "end_turn"])
def test_exhausted_more_preserves_guardrail_and_refusal_handling(gate: str) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    text = BLOCKED if gate == "guardrail_intervened" else '{"refusal":"purchase"}'
    result = run_chat(
        FakeLLM([_reply([_text_block(text)], gate)]),
        "more",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
        model_prose=True,
    )
    assert result["answer"] != NO_MORE
    assert result["exhausted_search"] == exhausted
    assert "choices" not in result and BLOCKED not in json.dumps(result)


@pytest.mark.parametrize(
    "forged",
    [
        {"query": "vegetarian"},
        {"query": "vegetarian", "offset": 39},
        {"offset": 0},
    ],
)
def test_forged_exhaustion_stops_before_provider(forged: dict[str, object]) -> None:
    provider = FakeLLM([])
    with pytest.raises(ChatProtocolError, match="previous_exhausted_search is invalid"):
        run_chat(provider, "more", budget(), PERIOD, previous_exhausted_search=forged)
    assert provider.requests == []


@pytest.mark.parametrize("equal_arguments", [False, True])
@pytest.mark.parametrize("model_prose", [False, True])
@pytest.mark.parametrize("message", ["more", "Start over", "more, but vegan"])
def test_combined_search_states_fail_before_provider(
    equal_arguments: bool, model_prose: bool, message: str
) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    next_search = (
        copy.deepcopy(exhausted)
        if equal_arguments
        else next_search_arguments(execute_catalog_search({"query": "chicken"}))
    )
    assert next_search is not None
    original = copy.deepcopy((next_search, exhausted))
    provider = FakeLLM([_search_reply({"query": "chicken"})])
    observed: list[list[dict[str, object]]] = []
    with pytest.raises(
        ChatProtocolError,
        match="^previous_search and previous_exhausted_search are mutually exclusive$",
    ) as caught:
        run_chat(
            provider,
            message,
            budget(),
            PERIOD,
            previous_search=next_search,
            previous_exhausted_search=exhausted,
            model_prose=model_prose,
            observe_terminal_tool_results=observed.append,
        )
    assert NO_MORE not in str(caught.value)
    assert provider.requests == observed == []
    assert (next_search, exhausted) == original


@pytest.mark.parametrize("invalid_next", [False, True])
@pytest.mark.parametrize("model_prose", [False, True])
def test_combined_state_preserves_individual_validation_errors(
    invalid_next: bool, model_prose: bool
) -> None:
    exhausted = terminal_search({"query": "vegetarian"})
    next_search = next_search_arguments(execute_catalog_search({"query": "chicken"}))
    assert next_search is not None
    field = "previous_search" if invalid_next else "previous_exhausted_search"
    provider = FakeLLM([_search_reply({"query": "chicken"})])
    with pytest.raises(ChatProtocolError, match=f"^{field} is invalid$"):
        run_chat(
            provider,
            "more",
            budget(),
            PERIOD,
            previous_search={"query": "zqxsentinel"} if invalid_next else next_search,
            previous_exhausted_search=(
                exhausted if invalid_next else {"query": "vegetarian"}
            ),
            model_prose=model_prose,
        )
    assert provider.requests == []


def test_exhaustion_uses_canonical_identity_for_a_model_assisted_more() -> None:
    exhausted = terminal_search({"query": "dairy free rice onion"})
    provider = FakeLLM([_search_reply({"query": "dairy free onion rice", "offset": 0})])
    result = run_chat(
        provider,
        "What else?",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    assert result["answer"] == NO_MORE
    assert result["exhausted_search"] == exhausted
    assert result["tool_trace"] == []
    assert "choices" not in result


@pytest.mark.parametrize(
    "message",
    [
        "Show the first page of zqxsentinel meals",
        "Show the first page of gluten free pasta meals",
        "Show the first page of rice zqxsentinel meals",
    ],
)
def test_invalid_restart_keeps_checked_exhaustion(message: str) -> None:
    exhausted = terminal_search(_constrained_cursor())
    result = run_chat(
        FakeLLM([_reply([_text_block("Please clarify.")], "end_turn")]),
        message,
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    assert result["exhausted_search"] == exhausted
    assert "next_search" not in result and "choices" not in result


@pytest.mark.parametrize(
    "arguments", [{"query": "unicorn"}, {"query": "gluten free pasta"}]
)
def test_unknown_or_dropped_search_does_not_repeat_exhausted_identity(
    arguments: dict[str, object],
) -> None:
    exhausted = terminal_search({"query": "omnivore"})
    result = run_chat(
        FakeLLM([_search_reply({**arguments, "offset": 9})]),
        "Find different meals instead",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    expected = execute_catalog_search(arguments)
    assert result["answer"] == catalog_answer(expected)
    assert result.get("next_search") == next_search_arguments(expected)
    assert "exhausted_search" not in result
    assert result.get("choices", []) == [
        {"recipe_id": rid} for rid in expected["recipe_ids"]
    ]


def test_exhaustion_validation_and_results_copy_nested_filters() -> None:
    exhausted = terminal_search(_constrained_cursor())
    original = copy.deepcopy(exhausted)
    checked = validated_previous_exhausted_search(exhausted)
    assert checked is not None
    cast(list[str], checked["tags"]).clear()
    cast(list[str], checked["exclude"]).clear()
    assert exhausted == original
    result = run_chat(
        FakeLLM([_reply([_text_block("Done.")], "end_turn")]),
        "more",
        budget(),
        PERIOD,
        previous_exhausted_search=exhausted,
    )
    stored = cast(dict[str, object], result["exhausted_search"])
    cast(list[str], stored["tags"]).clear()
    cast(list[str], stored["exclude"]).clear()
    assert exhausted == original
