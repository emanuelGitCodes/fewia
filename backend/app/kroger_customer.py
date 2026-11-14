"""Encrypt customer tokens and redact sensitive access-log queries."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.kroger_models import KrogerCustomerToken
from app.providers.kroger import (
    TOKEN_MARGIN_SECONDS,
    CustomerTokens,
    KrogerAuthRejected,
    KrogerClient,
)
from app.security_models import KrogerOwner
from app.services.security_admission import OwnerUnavailableError, lock_active_owner

CALLBACK_PATH = "/grocery/kroger/callback"
START_PATH = "/grocery/kroger/connect/start"


class KrogerConnectionChanged(Exception):
    """Reject a token lookup when the claimed connection no longer matches."""

    def __init__(self) -> None:
        super().__init__("Kroger account is not connected")


def store_tokens(
    session: Session, user_id: int, cipher: Fernet, tokens: CustomerTokens
) -> None:
    """Replace the user's token row with freshly encrypted tokens."""
    now = datetime.now(UTC)
    access = cipher.encrypt(tokens.access_token.encode())
    refresh = cipher.encrypt(tokens.refresh_token.encode())
    expires_at = now + timedelta(seconds=tokens.expires_in)
    row = session.get(KrogerCustomerToken, user_id)
    if row is None:
        session.add(
            KrogerCustomerToken(
                user_id=user_id,
                connection_version=uuid4(),
                access_token=access,
                refresh_token=refresh,
                access_expires_at=expires_at,
            )
        )
    else:
        row.connection_version = uuid4()
        row.access_token = access
        row.refresh_token = refresh
        row.access_expires_at = expires_at
        row.updated_at = now
    session.flush()


def is_connected(session: Session, user_id: int) -> bool:
    return session.get(KrogerCustomerToken, user_id) is not None


def delete_tokens(session: Session, user_id: int) -> None:
    """Forget the user's Kroger tokens. No error when there are none."""
    session.execute(
        delete(KrogerCustomerToken).where(KrogerCustomerToken.user_id == user_id)
    )
    session.flush()


def _locked_tokens(session: Session, user_id: int) -> KrogerCustomerToken | None:
    return session.scalars(
        select(KrogerCustomerToken)
        .where(KrogerCustomerToken.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def _fresh_access(row: KrogerCustomerToken | None, cipher: Fernet) -> str | None:
    if row is None:
        return None
    expires_at = row.access_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at - timedelta(seconds=TOKEN_MARGIN_SECONDS) <= datetime.now(UTC):
        return None
    try:
        return cipher.decrypt(row.access_token).decode()
    except (InvalidToken, UnicodeError):
        return None


def delete_rejected_access_token(
    session: Session,
    user_id: int,
    cipher: Fernet,
    rejected_token: str,
    *,
    expected_connection_version: UUID | None = None,
) -> bool:
    """Delete only the token pair that contains the rejected access token."""
    row = _locked_tokens(session, user_id)
    if row is None:
        return False
    if expected_connection_version is not None and not secrets.compare_digest(
        str(row.connection_version), str(expected_connection_version)
    ):
        return False
    try:
        current = cipher.decrypt(row.access_token)
    except InvalidToken:
        return False
    if not secrets.compare_digest(current, rejected_token.encode()):
        return False
    session.delete(row)
    session.flush()
    return True


def _same_pair(
    row: KrogerCustomerToken | None,
    version: UUID,
    access: bytes,
    refresh: bytes,
) -> bool:
    return (
        row is not None
        and row.connection_version == version
        and secrets.compare_digest(row.access_token, access)
        and secrets.compare_digest(row.refresh_token, refresh)
    )


def _connection_tokens(
    session: Session,
    user_id: int,
    expected_connection_version: UUID | None,
    expected_pairing_generation: UUID | None,
) -> KrogerCustomerToken | None:
    if expected_connection_version is None and expected_pairing_generation is None:
        return _locked_tokens(session, user_id)
    if expected_connection_version is None or expected_pairing_generation is None:
        raise KrogerConnectionChanged()
    try:
        lock_active_owner(session, user_id)
    except OwnerUnavailableError:
        raise KrogerConnectionChanged() from None
    owner = session.scalar(
        select(KrogerOwner)
        .where(KrogerOwner.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if owner is None or owner.pairing_generation != expected_pairing_generation:
        raise KrogerConnectionChanged()
    row = _locked_tokens(session, user_id)
    if row is None or row.connection_version != expected_connection_version:
        raise KrogerConnectionChanged()
    return row


def customer_access_token(
    session: Session,
    user_id: int,
    client: KrogerClient,
    cipher: Fernet,
    *,
    expected_connection_version: UUID | None = None,
    expected_pairing_generation: UUID | None = None,
) -> str | None:
    """Refresh outside row locks, then store only if the token pair still matches.

    Callers MUST enter without database locks. Bound lookups commit before refresh I/O.
    Callers MUST commit changes before further provider calls.
    """
    bound = (
        expected_connection_version is not None
        or expected_pairing_generation is not None
    )
    if bound:
        row = _connection_tokens(
            session, user_id, expected_connection_version, expected_pairing_generation
        )
    else:
        row = session.scalars(
            select(KrogerCustomerToken)
            .where(KrogerCustomerToken.user_id == user_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
    if row is None:
        return None
    access = _fresh_access(row, cipher)
    if access is not None:
        return access
    version = row.connection_version
    original_access, original_refresh = row.access_token, row.refresh_token
    try:
        secret = cipher.decrypt(original_refresh).decode()
        cipher.decrypt(original_access).decode()
    except (InvalidToken, UnicodeError):
        current = _connection_tokens(
            session, user_id, expected_connection_version, expected_pairing_generation
        )
        if _same_pair(current, version, original_access, original_refresh):
            assert current is not None
            session.delete(current)
            session.flush()
            return None
        return _fresh_access(current, cipher)
    if bound:
        session.commit()
    try:
        tokens = client.refresh_customer(secret)
    except KrogerAuthRejected:
        current = _connection_tokens(
            session, user_id, expected_connection_version, expected_pairing_generation
        )
        if _same_pair(current, version, original_access, original_refresh):
            assert current is not None
            session.delete(current)
            session.flush()
            return None
        return _fresh_access(current, cipher)
    current = _connection_tokens(
        session, user_id, expected_connection_version, expected_pairing_generation
    )
    if not _same_pair(current, version, original_access, original_refresh):
        return _fresh_access(current, cipher)
    assert current is not None
    current.access_token = cipher.encrypt(tokens.access_token.encode())
    current.refresh_token = cipher.encrypt(tokens.refresh_token.encode())
    current.access_expires_at = datetime.now(UTC) + timedelta(seconds=tokens.expires_in)
    current.updated_at = datetime.now(UTC)
    session.flush()
    return tokens.access_token


class _RedactCallbackQuery(logging.Filter):
    """Remove sensitive query values from the server access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > 2 and isinstance(args[2], str):
            path = args[2].split("?", 1)[0]
            route = unquote(path).removeprefix("/api")
            if route in (
                CALLBACK_PATH,
                START_PATH,
                "/grocery/kroger/fixture/v1/connect/oauth2/authorize",
            ):
                record.args = (*args[:2], path, *args[3:])
        return True


def redact_access_log() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _RedactCallbackQuery) for f in logger.filters):
        logger.addFilter(_RedactCallbackQuery())
