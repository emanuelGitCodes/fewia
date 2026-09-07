"""Dispatch one Instacart development shopping-list handoff."""

from collections.abc import Callable
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.handoff_models import ShoppingHandoff
from app.providers.instacart import InstacartRejected, validate_link_url
from app.services.handoff_intents import (
    _LIFE,
    HandoffNotFound,
    HandoffView,
    _aware_utc,
    _lock,
    _require_owner,
    _view,
    validated_cached_payload,
)


class HandoffLinkProvider(Protocol):
    def create_link(self, payload: dict[str, object]) -> str: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _may_start(
    row: ShoppingHandoff, retry: bool, expected: object, view: HandoffView
) -> bool:
    if retry is False:
        return row.state == "prepared"
    if type(expected) is not int or expected != row.attempts:
        return False
    if row.state in {"uncertain", "failed"}:
        return True
    return row.state == "succeeded" and view.retry_allowed


def _owned_view(
    session: Session, user_id: int, handoff_id: str, clock: datetime
) -> HandoffView:
    row = _lock(session, user_id, handoff_id, None)
    if row is None:
        raise HandoffNotFound()
    return _view(row, clock)


def _claim(
    session: Session, row: ShoppingHandoff, token: str, clock: datetime, retry: bool
) -> str | None:
    return session.scalar(
        update(ShoppingHandoff)
        .where(
            ShoppingHandoff.id == row.id,
            ShoppingHandoff.user_id == row.user_id,
            ShoppingHandoff.state == row.state,
            ShoppingHandoff.attempts == row.attempts,
        )
        .values(
            state="dispatching",
            attempts=ShoppingHandoff.attempts + 1,
            attempt_token=token,
            started_at=clock,
            retry_authorized_at=clock if retry else None,
            url=None,
            error_code=None,
            expires_at=None,
        )
        .execution_options(synchronize_session=False)
        .returning(ShoppingHandoff.id)
    )


def _finish(
    session: Session,
    user_id: int,
    handoff_id: str,
    token: str,
    url: str | None,
    rejected: bool,
    started: datetime,
) -> None:
    code = "instacart_rejected" if rejected else "instacart_uncertain"
    values: dict[str, object] = {
        "state": "succeeded" if url else "failed" if rejected else "uncertain",
        "url": url,
        "error_code": None if url else code,
        "expires_at": started + _LIFE if url else None,
    }
    session.execute(
        update(ShoppingHandoff)
        .where(
            ShoppingHandoff.id == handoff_id,
            ShoppingHandoff.user_id == user_id,
            ShoppingHandoff.state == "dispatching",
            ShoppingHandoff.attempt_token == token,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )


def dispatch_handoff(
    factory: sessionmaker[Session],
    provider: HandoffLinkProvider,
    user_id: int,
    handoff_id: str,
    *,
    retry: bool = False,
    expected_attempt: int | None = None,
    now: Callable[[], datetime] = _now,
) -> HandoffView:
    user_id = _require_owner(user_id)
    if type(handoff_id) is not str or not handoff_id:
        raise HandoffNotFound()
    if type(retry) is not bool:
        raise ValueError("retry MUST be a boolean")
    clock = _aware_utc(now())
    token = ""
    payload: dict[str, object] = {}
    with factory.begin() as session:
        presented = _owned_view(session, user_id, handoff_id, clock)
        row = _lock(session, user_id, handoff_id, None)
        if row is None or not _may_start(row, retry, expected_attempt, presented):
            return presented
        payload = validated_cached_payload(row.request_payload, row.request_hash)
        token = token_urlsafe(32)
        if _claim(session, row, token, clock, retry) is None:
            session.expire_all()
            return _owned_view(session, user_id, handoff_id, clock)
    url: str | None = None
    rejected = False
    try:
        url = validate_link_url(provider.create_link(payload))
    except InstacartRejected:
        rejected = True
    except Exception:
        url = None
    with factory.begin() as session:
        _finish(session, user_id, handoff_id, token, url, rejected, clock)
        return _owned_view(session, user_id, handoff_id, _aware_utc(now()))
