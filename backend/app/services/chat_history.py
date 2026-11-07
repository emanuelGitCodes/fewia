"""Load stored chat context for a follow-up job."""

from copy import deepcopy
from typing import NoReturn, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.catalog_tool import exhausted_page_arguments, page_arguments
from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN, plan_ingredient_ids
from app.agent.chat_messages import is_guardrail_decline, next_what_if_recipe
from app.domain.grocery import GroceryRequest
from app.job_models import Job
from app.services.chat_job import ChatHistoryTurn

_UNAVAILABLE = "Chat context is unavailable."
_ELLIPSIS = "..."
_USER = "user"
_ASSISTANT = "assistant"


class ChatContextUnavailable(Exception):
    pass


def _fail() -> NoReturn:
    raise ChatContextUnavailable(_UNAVAILABLE)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail()
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            _fail()
        mapped[key] = item
    return mapped


def _copy_request(value: object) -> dict[str, object]:
    dumped: object = None
    try:
        dumped = GroceryRequest.model_validate(value).model_dump(mode="json")
    except ValidationError:
        dumped = None
    if not isinstance(dumped, dict):
        _fail()
    return cast(dict[str, object], dumped)


def _previous_request(
    result: dict[str, object],
    payload: dict[str, object],
    *,
    chat: bool,
) -> dict[str, object] | None:
    raw = result.get("request")
    if raw is not None:
        return _copy_request(raw)
    if not chat:
        if "request" not in payload:
            _fail()
        return _copy_request(payload["request"])
    previous = payload.get("previous_request")
    if previous is None:
        return None
    return _copy_request(previous)


def _turn(item: object) -> ChatHistoryTurn:
    parsed: ChatHistoryTurn | None = None
    try:
        parsed = ChatHistoryTurn.model_validate(item)
    except ValidationError:
        parsed = None
    if parsed is None:
        _fail()
    return parsed


def _history(value: object) -> list[ChatHistoryTurn]:
    if not isinstance(value, list) or len(value) > MAX_HISTORY or len(value) % 2:
        _fail()
    turns: list[ChatHistoryTurn] = []
    for index, item in enumerate(value):
        turn = _turn(item)
        expected = _USER if index % 2 == 0 else _ASSISTANT
        if turn.role != expected:
            _fail()
        turns.append(turn)
    return turns


def _assistant_turn(value: object) -> ChatHistoryTurn:
    if not isinstance(value, str):
        _fail()
    text = value.strip()
    if not text:
        _fail()
    if len(text) > MAX_MESSAGE_LEN:
        text = text[: MAX_MESSAGE_LEN - len(_ELLIPSIS)] + _ELLIPSIS
    return _turn({"role": _ASSISTANT, "text": text})


def _public(turn: ChatHistoryTurn) -> dict[str, str]:
    return {"role": str(turn.role), "text": turn.text}


def _chat_context(
    payload: dict[str, object], result: dict[str, object]
) -> tuple[list[dict[str, str]], dict[str, object] | None]:
    raw_history: object = payload["history"] if "history" in payload else []
    turns = _history(raw_history)
    if not is_guardrail_decline(result):
        user_turn = _turn({"role": _USER, "text": payload.get("message")})
        turns = [*turns, user_turn, _assistant_turn(result.get("answer"))]
        turns = turns[-MAX_HISTORY:]
    return [_public(turn) for turn in turns], _previous_request(
        result, payload, chat=True
    )


def _previous_job(
    session: Session, user_id: int, previous_job_id: str | UUID | None
) -> Job | None:
    if type(user_id) is not int or user_id < 1:
        _fail()
    if previous_job_id is None:
        return None
    job = session.scalar(
        select(Job).where(
            Job.id == str(previous_job_id),
            Job.user_id == user_id,
            Job.kind == "agent",
        )
    )
    if job is None or job.status != "succeeded":
        _fail()
    return job


def _search_state(
    result: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    search = page_arguments(result.get("next_search"))
    exhausted = exhausted_page_arguments(result.get("exhausted_search"))
    if search is not None and exhausted is not None:
        _fail()
    return deepcopy(search), deepcopy(exhausted)


def load_previous_search_state(
    session: Session,
    user_id: int,
    previous_job_id: str | UUID | None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    job = _previous_job(session, user_id, previous_job_id)
    if job is None:
        return None, None
    return _search_state(_mapping(job.result))


def load_previous_what_if(
    session: Session,
    user_id: int,
    previous_job_id: str | UUID | None,
) -> str | None:
    job = _previous_job(session, user_id, previous_job_id)
    if job is None:
        return None
    previous = _mapping(job.payload).get("previous_what_if_recipe")
    return next_what_if_recipe(
        _mapping(job.result), previous if isinstance(previous, str) else None
    )


def load_chat_context(
    session: Session,
    user_id: int,
    previous_job_id: str | UUID | None,
) -> tuple[list[dict[str, str]], dict[str, object] | None, list[str] | None]:
    job = _previous_job(session, user_id, previous_job_id)
    if job is None:
        return [], None, None
    payload = _mapping(job.payload)
    result = _mapping(job.result)
    ingredient_ids = plan_ingredient_ids(result.get("plan"))
    if payload.get("operation") == "chat":
        history, previous = _chat_context(payload, result)
        return history, previous, ingredient_ids
    if "operation" in payload:
        _fail()
    return [], _previous_request(result, payload, chat=False), ingredient_ids
