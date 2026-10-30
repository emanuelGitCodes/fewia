"""Tests for server-owned chat history loading."""

import copy
import json
from typing import cast
from uuid import UUID, uuid4

import pytest
from conftest import UserSeeder
from sqlalchemy.orm import Session

from app.agent.chat_context import MAX_MESSAGE_LEN
from app.domain.grocery import GroceryRequest
from app.job_models import Job
from app.services.chat_history import ChatContextUnavailable, load_chat_context
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
