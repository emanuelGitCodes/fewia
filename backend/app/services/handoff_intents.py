"""Cache Instacart development shopping-list handoff intents."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.handoff_models import ShoppingHandoff
from app.models import User as _User
from app.services.handoff_contract import (
    _LIFE as _LIFE,
)
from app.services.handoff_contract import (
    PAYLOAD_MISMATCH,
    STORE_FAILED,
    _canonical_json,
    is_handoff_unique_conflict,
)
from app.services.handoff_contract import (
    HandoffNotFound as HandoffNotFound,
)
from app.services.handoff_contract import (
    HandoffView as HandoffView,
)
from app.services.handoff_contract import (
    _aware_utc as _aware_utc,
)
from app.services.handoff_contract import (
    _json_copy as _json_copy,
)
from app.services.handoff_contract import (
    _require_owner as _require_owner,
)
from app.services.handoff_contract import (
    _view as _view,
)
from app.services.handoff_contract import (
    validated_cached_payload as validated_cached_payload,
)
from app.services.shopping_payload import shopping_payload_hash

_USER_TABLE = _User.__table__
__all__ = [
    "HandoffNotFound",
    "HandoffView",
    "_LIFE",
    "_aware_utc",
    "_json_copy",
    "_lock",
    "_require_owner",
    "_view",
    "prepare_handoff",
    "read_handoff",
    "validated_cached_payload",
]


def _lock(
    session: Session, user_id: int, handoff_id: str | None, digest: str | None
) -> ShoppingHandoff | None:
    query = select(ShoppingHandoff).where(ShoppingHandoff.user_id == user_id)
    if handoff_id is not None:
        query = query.where(ShoppingHandoff.id == handoff_id)
    if digest is not None:
        query = query.where(ShoppingHandoff.request_hash == digest)
    return session.execute(query.with_for_update()).scalar_one_or_none()


def prepare_handoff(
    factory: sessionmaker[Session],
    user_id: int,
    payload: dict[str, object],
    *,
    now: datetime | None = None,
) -> HandoffView:
    user_id = _require_owner(user_id)
    clock = datetime.now(UTC) if now is None else _aware_utc(now)
    digest = shopping_payload_hash(payload)
    stored = _json_copy(payload)
    with factory.begin() as session:
        row = _lock(session, user_id, None, digest)
        if row is None:
            inserted = ShoppingHandoff(
                user_id=user_id, request_hash=digest, request_payload=stored
            )
            conflict = False
            failed = False
            try:
                with session.begin_nested():
                    session.add(inserted)
                    session.flush()
            except IntegrityError as exc:
                failed = True
                conflict = is_handoff_unique_conflict(exc)
            row = inserted
            if failed and conflict:
                row = _lock(session, user_id, None, digest)
            elif failed:
                row = None
            if row is None:
                raise ValueError(STORE_FAILED)
        cached = validated_cached_payload(row.request_payload, row.request_hash)
        if _canonical_json(cached) != _canonical_json(stored):
            raise ValueError(PAYLOAD_MISMATCH)
        return _view(row, clock)


def read_handoff(
    factory: sessionmaker[Session],
    user_id: int,
    handoff_id: str,
    *,
    now: datetime | None = None,
) -> HandoffView | None:
    user_id = _require_owner(user_id)
    if type(handoff_id) is not str or not handoff_id:
        return None
    clock = datetime.now(UTC) if now is None else _aware_utc(now)
    with factory.begin() as session:
        row = _lock(session, user_id, handoff_id, None)
        return None if row is None else _view(row, clock)
