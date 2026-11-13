"""Reserve action quotas in the caller's transaction."""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import User
from app.security_models import QuotaCounter

Action = Literal["mutation", "retailer"]
MUTATION_USER_LIMIT: Final[int] = 60
RETAILER_USER_LIMIT: Final[int] = 10
RETAILER_GLOBAL_LIMIT: Final[int] = 100
_SAFE_MESSAGE: Final[str] = "Action limit reached. Try again later."


class AdmissionLimitError(Exception):
    """Report a quota refusal without owner or usage details."""

    status_code: Final[int] = 429

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(_SAFE_MESSAGE)


class OwnerUnavailableError(Exception):
    """Report an unavailable owner without account details."""

    status_code: Final[int] = 403

    def __init__(self) -> None:
        super().__init__("Action owner is unavailable.")


def _lock_key(action: Action, scope: str, scope_key: int) -> int:
    digest = hashlib.sha256(
        f"fewia:security_admission:{action}:{scope}:{scope_key}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def reserve_action(
    session: Session,
    user_id: int,
    action: Action,
    *,
    now: datetime | None = None,
) -> None:
    """Reserve one new action without committing.

    Callers MUST commit a successful reservation before a provider request.
    Callers MUST reserve only new actions after their idempotency checks.
    PostgreSQL keeps the active owner row locked until the caller commits or rolls back.
    SQLite supports fixture operations without concurrency guarantees.
    The now argument supplies a deterministic test clock.
    """
    if action not in ("mutation", "retailer"):
        raise ValueError("Action is invalid.")
    if type(user_id) is not int or not 0 < user_id <= 9223372036854775807:
        raise ValueError("Action owner is invalid.")
    if now is not None and now.utcoffset() is None:
        raise ValueError("Action time requires a timezone.")
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError("Action admission is unavailable.")

    quotas: list[tuple[str, int, int]] = (
        [("global", 0, RETAILER_GLOBAL_LIMIT), ("user", user_id, RETAILER_USER_LIMIT)]
        if action == "retailer"
        else [("user", user_id, MUTATION_USER_LIMIT)]
    )
    table = QuotaCounter.__table__
    with session.no_autoflush:
        if dialect == "postgresql" and action == "retailer":
            session.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _lock_key(action, "global", 0)},
            )
        owner_id = session.scalar(
            sa.select(User.id)
            .where(User.id == user_id, User.status == "active")
            .with_for_update()
        )
        if owner_id is None:
            raise OwnerUnavailableError()
        if dialect == "postgresql":
            session.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _lock_key(action, "user", user_id)},
            )

        current = now
        if current is None:
            if dialect == "postgresql":
                current = session.scalar(
                    sa.select(sa.func.clock_timestamp(type_=sa.DateTime(timezone=True)))
                )
            else:
                current = session.scalar(
                    sa.select(sa.func.current_timestamp(type_=sa.DateTime()))
                )
                if isinstance(current, datetime) and current.utcoffset() is None:
                    current = current.replace(tzinfo=UTC)
        if not isinstance(current, datetime) or current.utcoffset() is None:
            raise ValueError("Action time requires a timezone.")
        current = current.astimezone(UTC)
        minute_start = current.replace(second=0, microsecond=0)
        expires_at = minute_start + timedelta(minutes=1)
        retry_after = max(1, math.ceil((expires_at - current).total_seconds()))
        counts: list[int | None] = []
        for scope, scope_key, limit in quotas:
            count = session.scalar(
                sa.select(table.c.count).where(
                    table.c.action == action,
                    table.c.scope == scope,
                    table.c.scope_key == scope_key,
                    table.c.minute_start == minute_start,
                )
            )
            if count is not None and count >= limit:
                raise AdmissionLimitError(retry_after)
            counts.append(count)

        for (scope, scope_key, _), count in zip(quotas, counts, strict=True):
            if count is None:
                session.execute(
                    sa.insert(QuotaCounter).values(
                        action=action,
                        scope=scope,
                        scope_key=scope_key,
                        minute_start=minute_start,
                        expires_at=expires_at,
                        count=1,
                    )
                )
            else:
                session.execute(
                    sa.update(QuotaCounter)
                    .where(
                        table.c.action == action,
                        table.c.scope == scope,
                        table.c.scope_key == scope_key,
                        table.c.minute_start == minute_start,
                    )
                    .values(count=table.c.count + 1)
                )
