"""Tests for server-owned chat history loading."""

import copy
import json
from typing import cast
from uuid import UUID, uuid4

import pytest
from conftest import UserSeeder
from sqlalchemy.orm import Session

from app.agent.catalog_tool import execute_catalog_search, next_search_arguments
from app.agent.chat_context import MAX_MESSAGE_LEN
from app.agent.chat_refusal import GUARDRAIL_DECLINE
from app.domain.grocery import GroceryRequest
from app.job_models import Job
from app.services.chat_history import (
    ChatContextUnavailable,
    load_chat_context,
    load_previous_search,
)
from tests.test_chat_loop import _SWAP_ANSWER
from tests.test_model_prose_opt_in import GROUNDED_PLAIN, SENTINEL, _run, _swap

PERIOD = "2026-09-01"
SECRET = "do-not-echo-raw-input"
UNAVAILABLE = "Chat context is unavailable."


def request_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def expected_request(raw: dict[str, object]) -> dict[str, object]:
    dumped = GroceryRequest.model_validate(raw).model_dump(mode="json")
    return cast(dict[str, object], dumped)


def spending() -> dict[str, object]:
    return {
        "period": PERIOD,
        "posted_cents": 18000,
        "pending_cents": 1200,
        "refreshed_at": "2026-09-02T12:00:00Z",
        "raw_ledger": [{"id": SECRET}],
    }


def pair(index: int) -> list[dict[str, str]]:
    return [
        {"role": "user", "text": f"user-{index}"},
        {"role": "assistant", "text": f"assistant-{index}"},
    ]


def chat_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "operation": "chat",
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
        "spending": spending(),
        "spending_source": "fixture",
        "history": [],
    }
    values.update(overrides)
    return values


def plan_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "request": request_body(),
        "monthly_limit_cents": 40000,
        "spending": spending(),
        "spending_source": "fixture",
    }
    values.update(overrides)
    return values


def add_job(
    session: Session,
    *,
    user_id: int,
    payload: dict[str, object],
    result: dict[str, object] | None,
    status: str = "succeeded",
    kind: str = "agent",
) -> Job:
    job = Job(
        user_id=user_id,
        kind=kind,
        request_key=str(uuid4()),
        payload=payload,
        result=result,
        status=status,
    )
    session.add(job)
    session.flush()
    return job


def assert_static(error: BaseException) -> None:
    assert str(error) == UNAVAILABLE
    assert SECRET not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_none_parent_returns_empty_context(session: Session) -> None:
    history, previous, _ingredient_ids = load_chat_context(session, 1, None)

    assert history == []
    assert previous is None
    assert _ingredient_ids is None


def _search_result(**overrides: object) -> dict[str, object]:
    first = execute_catalog_search({"query": "vegetarian"})
    next_search = next_search_arguments(first)
    assert next_search is not None
    result: dict[str, object] = {"answer": "Catalog choices."}
    result["next_search"] = next_search
    result.update(overrides)
    return result


def test_previous_search_is_the_stored_next_search(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    result = _search_result()
    job = add_job(session, user_id=1, payload=chat_payload(), result=result)

    assert load_previous_search(session, 1, None) is None
    loaded = load_previous_search(session, 1, job.id)
    assert loaded == result["next_search"]
    assert loaded is not None and loaded["offset"] == 3
    history, _previous, _ids = load_chat_context(session, 1, job.id)
    assert history[-1] == {"role": "assistant", "text": "Catalog choices."}


def test_previous_search_is_none_without_a_next_search(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    result: dict[str, object] = {"answer": "Done."}
    job = add_job(session, user_id=1, payload=chat_payload(), result=result)
    assert load_previous_search(session, 1, job.id) is None


@pytest.mark.parametrize("tool", [None, "get_budget_summary", "get_meal"])
def test_intervening_turn_without_result_cursor_ignores_the_payload(
    session: Session, seed_user: UserSeeder, tool: str | None
) -> None:
    seed_user(1)
    cursor = _search_result()["next_search"]
    payload = chat_payload(message="thanks", previous_search=cursor)
    result = {
        "answer": "Done.",
        "tool_trace": [] if tool is None else [{"tool": tool, "outcome": "success"}],
    }
    job = add_job(session, user_id=1, payload=payload, result=result)
    assert load_previous_search(session, 1, job.id) is None


@pytest.mark.parametrize("tool", [None, "get_budget_summary", "get_meal"])
def test_intervening_turn_restores_only_the_checked_result_cursor(
    session: Session, seed_user: UserSeeder, tool: str | None
) -> None:
    seed_user(1)
    result = _search_result(
        tool_trace=[] if tool is None else [{"tool": tool, "outcome": "success"}]
    )
    payload = chat_payload(message="thanks", previous_search={"query": "chicken"})
    original_result = copy.deepcopy(result)
    original_payload = copy.deepcopy(payload)
    job = add_job(session, user_id=1, payload=payload, result=result)
    assert load_previous_search(session, 1, job.id) == result["next_search"]
    assert job.result == original_result
    assert job.payload == original_payload


def test_restored_cursor_does_not_share_nested_values_with_the_job(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    result = _search_result()
    job = add_job(session, user_id=1, payload=chat_payload(), result=result)
    original = copy.deepcopy(result)
    loaded = load_previous_search(session, 1, job.id)
    assert loaded is not None
    cast(list[str], loaded["tags"]).clear()
    assert job.result == original
    cast(list[str], loaded["exclude"]).append("eggs")
    assert job.result == original
    stored_result = cast(dict[str, object], job.result)
    stored = cast(dict[str, object], stored_result["next_search"])
    cast(list[str], stored["tags"]).append("unknown")
    assert loaded["tags"] == []
    again = load_previous_search(session, 1, job.id)
    assert again is None


@pytest.mark.parametrize("outcome", ["success", "error"])
def test_a_catalog_turn_does_not_resurrect_the_payload_cursor(
    session: Session, seed_user: UserSeeder, outcome: str
) -> None:
    seed_user(1)
    cursor = _search_result()["next_search"]
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_search=cursor),
        result={
            "answer": "No more matching meals.",
            "tool_trace": [{"tool": "search_meals", "outcome": outcome}],
        },
    )
    assert load_previous_search(session, 1, job.id) is None


def test_an_explicitly_cleared_cursor_does_not_use_the_payload(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    cursor = _search_result()["next_search"]
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_search=cursor),
        result={"answer": "Done.", "next_search": None},
    )
    assert load_previous_search(session, 1, job.id) is None


@pytest.mark.parametrize(
    "forged",
    [
        {"query": "meals", "tags": ["unknown"], "offset": 3},
        {"query": "vegetarian", "offset": 40},
        {"query": "vegetarian", "offset": True},
        {"query": "zqxsentinel"},
        ["vegetarian"],
    ],
)
def test_intervening_turn_ignores_the_payload_cursor(
    session: Session, seed_user: UserSeeder, forged: object
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_search=forged),
        result={"answer": "Done.", "tool_trace": []},
    )
    assert load_previous_search(session, 1, job.id) is None


@pytest.mark.parametrize(
    "forged",
    [
        {"query": "meals", "tags": ["no_such_tag"], "offset": 3},
        {"query": "vegetarian", "offset": 40},
        {"query": "vegetarian", "offset": 39, "limit": 3, "extra": 1},
        {"query": "zqxsentinel", "offset": 3},
        {"offset": 3},
        "vegetarian",
        ["vegetarian"],
        3,
        None,
    ],
)
def test_forged_next_search_loads_as_none(
    session: Session, seed_user: UserSeeder, forged: object
) -> None:
    seed_user(1)
    result = _search_result(next_search=forged)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_search=_search_result()["next_search"]),
        result=result,
    )
    assert load_previous_search(session, 1, job.id) is None


def test_previous_search_checks_the_job_like_the_chat_context(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    seed_user(2)
    result = _search_result()
    foreign = add_job(session, user_id=2, payload=chat_payload(), result=result)
    pending = add_job(
        session, user_id=1, payload=chat_payload(), result=result, status="queued"
    )
    for job in (foreign, pending):
        with pytest.raises(ChatContextUnavailable):
            load_previous_search(session, 1, job.id)
    with pytest.raises(ChatContextUnavailable):
        load_previous_search(session, 1, uuid4())


def test_rejected_model_text_is_not_in_the_loaded_next_turn(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    rejected = f"{SENTINEL} adds 999 kcal."
    first, _ = _run(_swap(rejected))
    assert first["reply_source"] == "template"
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message="swap chicken for chickpeas"),
        result=first,
    )

    history, _previous, _ids = load_chat_context(session, 1, job.id)
    assert SENTINEL not in json.dumps(history)
    assert history[-1] == {"role": "assistant", "text": _SWAP_ANSWER}

    _, second = _run(_swap(GROUNDED_PLAIN), history=history)
    assert SENTINEL not in json.dumps(second.requests)
    assert _SWAP_ANSWER in json.dumps(second.requests[0]["messages"])


def test_accepted_model_text_is_what_the_loaded_next_turn_replays(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    first, _ = _run(_swap(GROUNDED_PLAIN))
    assert first["reply_source"] == "model"
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message="swap chicken for chickpeas"),
        result=first,
    )
    history, _previous, _ids = load_chat_context(session, 1, job.id)
    assert history[-1] == {"role": "assistant", "text": GROUNDED_PLAIN}


@pytest.mark.parametrize("model_prose", [False, True])
def test_guardrail_blocked_turn_is_dropped_from_history(
    session: Session, seed_user: UserSeeder, model_prose: bool
) -> None:
    seed_user(1)
    blocked = {
        "answer": GUARDRAIL_DECLINE,
        "reply_check": {"gate": "guardrail"} if model_prose else None,
        "request": request_body(),
    }
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message="do what I asked above", history=pair(0)),
        result=blocked,
    )

    history, _previous, _ids = load_chat_context(session, 1, job.id)

    assert history == pair(0)
    assert "do what I asked above" not in json.dumps(history)


def test_normal_turn_keeps_both_turns_in_history(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message="hello", history=pair(0)),
        result={
            "answer": "Hi.",
            "reply_check": {"gate": "clean"},
            "request": request_body(),
        },
    )

    history, _previous, _ids = load_chat_context(session, 1, job.id)

    assert history == [
        *pair(0),
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "Hi."},
    ]


def test_owner_isolation_and_foreign_job(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    seed_user(2)
    owned = add_job(
        session,
        user_id=1,
        payload=chat_payload(),
        result={
            "answer": "Here is a labeled estimate.",
            "request": request_body(),
        },
    )
    foreign = add_job(
        session,
        user_id=2,
        payload=chat_payload(message=SECRET),
        result={"answer": SECRET, "request": request_body()},
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, owned.id)
    assert history == [
        {"role": "user", "text": "plan chicken tacos"},
        {"role": "assistant", "text": "Here is a labeled estimate."},
    ]
    assert previous == expected_request(request_body())

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, foreign.id)
    assert_static(caught.value)
    with pytest.raises(ChatContextUnavailable) as foreign_owner:
        load_chat_context(session, 2, owned.id)
    assert_static(foreign_owner.value)


def test_load_accepts_uuid_job_id(session: Session, seed_user: UserSeeder) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(),
        result={"request": request_body()},
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, UUID(job.id))

    assert history == []
    assert previous == expected_request(request_body())


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_unusable_status_is_static(
    session: Session, seed_user: UserSeeder, status: str
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(),
        result={"answer": "ok", "request": request_body()},
        status=status,
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


def test_missing_job_is_static(session: Session, seed_user: UserSeeder) -> None:
    seed_user(1)

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, uuid4())
    assert_static(caught.value)


def test_sync_kind_is_static(session: Session, seed_user: UserSeeder) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(),
        result={"request": request_body()},
        kind="sync",
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


def test_legacy_plan_result_without_request(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(),
        result={"plan": {"accepted": True}, "tool_trace": [SECRET]},
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history == []
    assert previous == expected_request(request_body())
    assert SECRET not in str(previous)


def test_plan_prefers_validated_result_request(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    result_request = request_body(meals=[{"recipe_id": "bean_tacos", "servings": 2}])
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(),
        result={"request": result_request},
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history == []
    assert previous == expected_request(result_request)
    assert job.result is not None
    assert previous is not job.result["request"]


def test_chat_followup_trims_to_last_four_pairs(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    stored_history: list[dict[str, str]] = []
    for index in range(1, 5):
        stored_history.extend(pair(index))
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(history=stored_history, message="user-5"),
        result={"answer": "assistant-5", "request": request_body()},
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert [item["text"] for item in history] == [
        "user-2",
        "assistant-2",
        "user-3",
        "assistant-3",
        "user-4",
        "assistant-4",
        "user-5",
        "assistant-5",
    ]
    assert [item["role"] for item in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert previous == expected_request(request_body())
    assert job.payload["history"] == stored_history


def test_invalid_roles_and_extra_history_data(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    assistant_first = add_job(
        session,
        user_id=1,
        payload=chat_payload(
            history=[
                {"role": "assistant", "text": "no"},
                {"role": "user", "text": "x"},
            ]
        ),
        result={"answer": "ok", "request": request_body()},
    )
    extra = add_job(
        session,
        user_id=1,
        payload=chat_payload(
            history=[
                {"role": "user", "text": "plan", "tool_trace": [SECRET]},
                {"role": "assistant", "text": "ok"},
            ]
        ),
        result={"answer": "ok", "request": request_body()},
    )

    with pytest.raises(ChatContextUnavailable) as first:
        load_chat_context(session, 1, assistant_first.id)
    assert_static(first.value)
    with pytest.raises(ChatContextUnavailable) as second:
        load_chat_context(session, 1, extra.id)
    assert_static(second.value)


def test_long_assistant_text_trims_copy(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    answer = "a" * (MAX_MESSAGE_LEN + 50)
    result: dict[str, object] = {
        "answer": answer,
        "request": request_body(),
        "tool_trace": [{"reasoning": SECRET}],
    }
    payload = chat_payload()
    original_payload = copy.deepcopy(payload)
    original_result = copy.deepcopy(result)
    job = add_job(session, user_id=1, payload=payload, result=result)

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history[0]["text"] == "plan chicken tacos"
    assert history[1]["role"] == "assistant"
    assert len(history[1]["text"]) == MAX_MESSAGE_LEN
    assert history[1]["text"].endswith("...")
    assert history[1]["text"][:-3] == "a" * (MAX_MESSAGE_LEN - 3)
    assert previous == expected_request(request_body())
    assert job.result is not None
    assert job.result["answer"] == answer
    assert job.payload == original_payload
    assert job.result == original_result


def test_preserves_full_user_message(session: Session, seed_user: UserSeeder) -> None:
    seed_user(1)
    message = "x" * MAX_MESSAGE_LEN
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message=message),
        result={"answer": "ok", "request": request_body()},
    )

    history, _previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history[0]["text"] == message
    assert len(history[0]["text"]) == MAX_MESSAGE_LEN


def test_chat_clarification_uses_payload_previous_request(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    previous_raw = request_body(meals=[{"recipe_id": "lentil_soup", "servings": 3}])
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_request=previous_raw),
        result={
            "status": "clarification",
            "answer": "How many servings?",
            "request": None,
        },
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history == [
        {"role": "user", "text": "plan chicken tacos"},
        {"role": "assistant", "text": "How many servings?"},
    ]
    assert previous == expected_request(previous_raw)
    assert previous is not job.payload["previous_request"]


def test_chat_clarification_without_previous_request(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(),
        result={
            "status": "clarification",
            "answer": "Which meals?",
            "request": None,
        },
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history[-1]["text"] == "Which meals?"
    assert previous is None


def test_invalid_previous_request_is_static(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(previous_request={"meals": [], "budget_period": PERIOD}),
        result={
            "status": "clarification",
            "answer": "Which meals?",
            "request": None,
        },
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


def test_invalid_result_request_does_not_fall_back(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(),
        result={"request": {"meals": [], "budget_period": PERIOD}},
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


def test_history_omits_tool_trace_and_spending(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(),
        result={
            "answer": "Here is a labeled estimate.",
            "request": request_body(),
            "tool_trace": [{"name": "plan_groceries", "input": SECRET}],
        },
    )

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert previous is not None
    for item in history:
        assert set(item) == {"role", "text"}
        assert SECRET not in item["text"]
    assert "raw_ledger" not in previous
    dumped = str(history) + str(previous)
    assert SECRET not in dumped
    assert "posted_cents" not in dumped


@pytest.mark.parametrize("owner", [True, False, 0, -1, 1.0])
def test_owner_must_be_positive_exact_int(
    session: Session, seed_user: UserSeeder, owner: object
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload(message=SECRET),
        result={"answer": SECRET, "request": request_body()},
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, cast(int, owner), job.id)
    assert_static(caught.value)
    with pytest.raises(ChatContextUnavailable) as none_parent:
        load_chat_context(session, cast(int, owner), None)
    assert_static(none_parent.value)


@pytest.mark.parametrize("operation", ["plan", None])
def test_plan_operation_loads_previous_request(
    session: Session, seed_user: UserSeeder, operation: str | None
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(operation=operation),
        result={"request": request_body()},
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


@pytest.mark.parametrize("operation", ["sync", "purchase", "", "CHAT"])
def test_unknown_operation_is_static(
    session: Session, seed_user: UserSeeder, operation: str
) -> None:
    seed_user(1)
    job = add_job(
        session,
        user_id=1,
        payload=plan_payload(operation=operation),
        result={"request": request_body(), "tool_trace": [SECRET]},
    )

    with pytest.raises(ChatContextUnavailable) as caught:
        load_chat_context(session, 1, job.id)
    assert_static(caught.value)


def test_assistant_whitespace_trimmed_before_truncation(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(1)
    answer = "  " + ("a" * (MAX_MESSAGE_LEN + 50)) + "  "
    result: dict[str, object] = {
        "answer": answer,
        "request": request_body(),
        "tool_trace": [{"reasoning": SECRET}],
    }
    payload = chat_payload()
    original_payload = copy.deepcopy(payload)
    original_result = copy.deepcopy(result)
    job = add_job(session, user_id=1, payload=payload, result=result)

    history, previous, _ingredient_ids = load_chat_context(session, 1, job.id)

    assert history[1]["role"] == "assistant"
    assert len(history[1]["text"]) == MAX_MESSAGE_LEN
    assert history[1]["text"].endswith("...")
    assert history[1]["text"][:-3] == "a" * (MAX_MESSAGE_LEN - 3)
    assert previous == expected_request(request_body())
    assert job.result is not None
    assert job.result["answer"] == answer
    assert job.payload == original_payload
    assert job.result == original_result
    assert SECRET not in history[1]["text"]


@pytest.mark.parametrize("chat", [False, True])
def test_previous_plan_ingredient_ids(
    session: Session, seed_user: UserSeeder, chat: bool
) -> None:
    seed_user(1)
    result: dict[str, object] = {
        "answer": "Here is a labeled estimate.",
        "request": request_body(),
        "plan": {
            "lines": [
                {"ingredient_id": "tortillas", "reasoningContent": SECRET},
                {"ingredient_id": "eggs"},
                {"ingredient_id": "eggs"},
                {"ingredient_id": "unknown"},
            ]
        },
    }
    job = add_job(
        session,
        user_id=1,
        payload=chat_payload() if chat else plan_payload(),
        result=result,
    )
    before = copy.deepcopy(job.result)
    loaded = load_chat_context(session, 1, job.id)
    assert len(loaded) == 3
    history, previous, ids = loaded
    assert len(history) == (2 if chat else 0)
    assert previous == expected_request(request_body())
    assert ids == ["eggs", "tortillas"]
    assert job.result == before
    assert SECRET not in str(loaded)
