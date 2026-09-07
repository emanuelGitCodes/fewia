"""Shared Instacart development shopping-list handoff contract."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.exc import IntegrityError

from app.handoff_models import ShoppingHandoff
from app.providers.instacart import validate_link_url
from app.services.shopping_payload import shopping_payload_hash

_STALE = timedelta(seconds=120)
_LIFE = timedelta(days=7)
_UNIQUE_HANDOFF = "uq_shopping_handoffs_user_request_hash"
PAYLOAD_MISMATCH = "shopping handoff payload does not match the cached plan"
STORE_FAILED = "shopping handoff could not be stored"
INVALID_CACHED_URL = "invalid_cached_url"


class HandoffNotFound(Exception):
    def __init__(self) -> None:
        super().__init__("shopping handoff is missing")


@dataclass(frozen=True)
class HandoffView:
    id: str
    state: str
    attempts: int
    url: str | None
    error_code: str | None
    expires_at: datetime | None
    retry_allowed: bool


def _aware_utc(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.tzinfo.utcoffset(value) is None
    ):
        raise ValueError("now MUST be a timezone-aware datetime")
    return value.astimezone(UTC)


def _db_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_owner(user_id: object) -> int:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id MUST be a positive integer")
    return user_id


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_copy(payload: dict[str, object]) -> dict[str, object]:
    copied: object = json.loads(_canonical_json(payload))
    if isinstance(copied, dict):
        return cast(dict[str, object], copied)
    raise ValueError("payload MUST be a JSON object")


def validated_cached_payload(payload: object, digest: object) -> dict[str, object]:
    if type(digest) is not str or not digest or not isinstance(payload, dict):
        raise ValueError(PAYLOAD_MISMATCH)
    typed = cast(dict[str, object], payload)
    computed: str | None
    try:
        computed = shopping_payload_hash(typed)
    except (TypeError, ValueError):
        computed = None
    if computed is None or computed != digest:
        raise ValueError(PAYLOAD_MISMATCH)
    return _json_copy(typed)


def is_handoff_unique_conflict(error: IntegrityError) -> bool:
    orig: object = error.orig
    if orig is None:
        return False
    sqlstate: object = getattr(orig, "sqlstate", None)
    if type(sqlstate) is not str:
        sqlstate = getattr(orig, "pgcode", None)
    diag: object = getattr(orig, "diag", None)
    constraint: object = None
    if diag is not None:
        constraint = getattr(diag, "constraint_name", None)
    if sqlstate == "23505" and constraint == _UNIQUE_HANDOFF:
        return True
    return getattr(orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE


def _view(row: ShoppingHandoff, now: datetime) -> HandoffView:
    started = _db_utc(row.started_at)
    if row.state == "dispatching" and started is not None and now - started > _STALE:
        row.state = "uncertain"
        row.error_code = "stale_dispatch"
        row.url = None
    expires = _db_utc(row.expires_at)
    if expires is None and started is not None:
        expires = started + _LIFE
    expired = row.state == "succeeded" and (expires is None or expires <= now)
    url: str | None = None
    if row.state == "succeeded" and not expired:
        candidate = row.url
        allowed: str | None = None
        if type(candidate) is str:
            try:
                allowed = validate_link_url(candidate)
            except ValueError:
                allowed = None
        if allowed is None:
            row.state = "uncertain"
            row.error_code = INVALID_CACHED_URL
            row.url = None
        else:
            url = allowed
    retry = row.state in {"uncertain", "failed"} or expired
    shown = None if expired else _db_utc(row.expires_at)
    return HandoffView(
        row.id, row.state, row.attempts, url, row.error_code, shown, retry
    )
