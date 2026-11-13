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


def lock_owner(session: Session, user_id: int) -> None:
    """Serialize owner writes until the caller commits or rolls back.

    Maintenance callers MUST take this lock before owner status changes or deletion.
    SQLite supports fixture operations without concurrency guarantees.
    """
    if type(user_id) is not int or not 0 < user_id <= 9223372036854775807:
        raise ValueError("Action owner is invalid.")
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError("Action admission is unavailable.")
    if dialect == "postgresql":
        digest = hashlib.sha256(f"fewia:owner:{user_id}".encode("ascii")).digest()
        session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(digest[:8], byteorder="big", signed=True)},
        )


def lock_active_owner(session: Session, user_id: int) -> User:
    """Lock and refresh an active owner without users write privileges."""
    with session.no_autoflush:
        lock_owner(session, user_id)
        owner = session.scalar(
            sa.select(User)
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        if owner is None or owner.status != "active":
            raise OwnerUnavailableError()
        return owner


def require_active_owner(session: Session, user_id: int) -> None:
    """Lock the owner, then read current status without users write privileges."""
    lock_active_owner(session, user_id)


def database_utc_now(session: Session) -> datetime:
    """Read the database wall clock in UTC."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        current = session.scalar(
            sa.select(sa.func.clock_timestamp(type_=sa.DateTime(timezone=True)))
        )
    elif dialect == "sqlite":
        current = session.scalar(
            sa.select(sa.func.current_timestamp(type_=sa.DateTime()))
        )
        if isinstance(current, datetime) and current.utcoffset() is None:
            current = current.replace(tzinfo=UTC)
    else:
        raise RuntimeError("Action admission is unavailable.")
    if not isinstance(current, datetime) or current.utcoffset() is None:
        raise ValueError("Action time requires a timezone.")
    return current.astimezone(UTC)


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
    PostgreSQL keeps the owner advisory lock until the caller commits or rolls back.
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
        require_active_owner(session, user_id)
        current = now if now is not None else database_utc_now(session)
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
