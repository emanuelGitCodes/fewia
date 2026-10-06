"""Load stored chat context for a follow-up job."""

from typing import NoReturn, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN, plan_ingredient_ids
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
    user_turn = _turn({"role": _USER, "text": payload.get("message")})
    turns = [*turns, user_turn, _assistant_turn(result.get("answer"))][-MAX_HISTORY:]
    return [_public(turn) for turn in turns], _previous_request(
        result, payload, chat=True
    )


def load_chat_context(
    session: Session,
    user_id: int,
    previous_job_id: str | UUID | None,
) -> tuple[list[dict[str, str]], dict[str, object] | None, list[str] | None]:
    if type(user_id) is not int or user_id < 1:
        _fail()
    if previous_job_id is None:
        return [], None, None
    job = session.scalar(
        select(Job).where(
            Job.id == str(previous_job_id),
            Job.user_id == user_id,
            Job.kind == "agent",
        )
    )
    if job is None or job.status != "succeeded":
        _fail()
    payload = _mapping(job.payload)
    result = _mapping(job.result)
    ingredient_ids = plan_ingredient_ids(result.get("plan"))
    if payload.get("operation") == "chat":
        history, previous = _chat_context(payload, result)
        return history, previous, ingredient_ids
    if "operation" in payload:
        _fail()
    return [], _previous_request(result, payload, chat=False), ingredient_ids
