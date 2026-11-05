from typing import cast

from test_chat_loop import PERIOD, FakeLLM, _search_reply, budget

from app.agent.catalog_tool import (
    catalog_answer,
    execute_catalog_search,
    next_search_arguments,
)
from app.agent.chat_loop import run_chat
from app.agent.chat_messages import tool_result_block


def test_reordered_search_continues_from_the_saved_page() -> None:
    first = execute_catalog_search({"query": "dairy free rice onion"})
    assert first["total_matches"] == 14
    cursor = next_search_arguments(first)
    assert cursor is not None and cursor["offset"] == 3
    expected = execute_catalog_search(cursor)
    next_cursor = next_search_arguments(expected)
    assert next_cursor is not None and next_cursor["offset"] == 6

    provider = FakeLLM([_search_reply({"query": "dairy free onion rice"})])
    observed: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        "What else?",
        budget(),
        PERIOD,
        previous_search=cursor,
        observe_terminal_tool_results=observed.append,
    )

    choices = cast(list[dict[str, str]], result["choices"])
    assert [choice["recipe_id"] for choice in choices] == expected["recipe_ids"]
    assert not set(cast(list[str], first["recipe_ids"])) & set(
        cast(list[str], expected["recipe_ids"])
    )
    assert result["answer"] == catalog_answer(expected)
    assert result["next_search"] == next_cursor
    assert observed == [[tool_result_block("d1", expected, success=True)]]
    assert len(provider.requests) == 1


def test_unknown_search_does_not_continue_an_omnivore_cursor() -> None:
    first = execute_catalog_search({"query": "omnivore"})
    cursor = next_search_arguments(first)
    assert cursor is not None and cursor["offset"] == 3
    arguments: dict[str, object] = {"query": "unicorn", "offset": 0}
    expected = execute_catalog_search(arguments)
    assert expected["status"] == "no_match" and expected["recipe_ids"] == []

    provider = FakeLLM([_search_reply(arguments)])
    observed: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        "Find unicorn meals",
        budget(),
        PERIOD,
        previous_search=cursor,
        observe_terminal_tool_results=observed.append,
    )

    assert "choices" not in result
    assert "next_search" not in result
    assert result["answer"] == catalog_answer(expected)
    assert observed == [[tool_result_block("d1", expected, success=True)]]
    assert len(provider.requests) == 1
